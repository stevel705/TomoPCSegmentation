import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import label as label_image
from icecream import ic
from skimage import exposure
from scipy.ndimage.morphology import binary_fill_holes
from skimage.filters import median

import data_manager as dm
from helper import crop, paste
import viewer


VOXEL_SIZE = 9 * 1e-6


def hide_image_elements(img, bin_mask):
    """
    where mask, change pixels' brightness min(img) value
    """
    bin_mask = bin_mask.astype(bool)
    bin_mask = binary_fill_holes(bin_mask)
    return bin_mask * np.min(img) + img * (~bin_mask.astype(bool))


def find_big_ones_clusters(bin_mask,
                           min_cluster_length=None,
                           min_cluster_order=None):
    labeled_mask, _ = label_image(bin_mask)
    cluster_labels, cluster_sizes = np.unique(labeled_mask,
                                               return_counts=True)

    # sort from max to min
    sorted_indexes = np.flip(cluster_sizes.argsort())
    cluster_sizes = cluster_sizes[sorted_indexes]
    cluster_labels = cluster_labels[sorted_indexes]

    min_cluster_length = cluster_sizes[min_cluster_order] if min_cluster_order else min_cluster_length
    big_clusters_indexes = cluster_sizes > min_cluster_length

    big_ones_cluster_labels = cluster_labels[big_clusters_indexes]

    #  TODO:refactor this part
    contour_mask = np.zeros(bin_mask.shape, dtype=bool)
    for label in big_ones_cluster_labels:
        if label == 0:
            continue
        contour_mask = np.logical_or(contour_mask, _create_mask_layer_for_label(labeled_mask, label))

    return contour_mask


def _create_mask_layer_for_label(labeled_img, label):
    mask = np.zeros(labeled_img.shape)
    mask +=  np.where(label == labeled_img, True, False)
    return mask.astype(bool)


def get_small_pores_mask(img2d_gray,
                         mask,
                         percentile_glob=2.5,
                         min_large_contour_length=2000,
                         window_size=200):

    # убираем большие контуры
    large_clusters_mask = find_big_ones_clusters(mask,
                                                 min_large_contour_length)
    img2d_gray = hide_image_elements(img2d_gray, large_clusters_mask) 
    global_thresh = np.percentile(img2d_gray.ravel(), percentile_glob)

    check_mask = find_big_ones_clusters(img2d_gray > global_thresh, min_large_contour_length)
    while np.any(check_mask):
        img2d_gray = hide_image_elements(img2d_gray, check_mask)
        check_mask = find_big_ones_clusters(img2d_gray > global_thresh, min_large_contour_length)
        print("deleting remnants")

    # количество маленьких окошек
    count_of_center_points_x, count_of_center_points_y = np.array(img2d_gray.shape) // window_size

    # выкидываем из изображения все, что вне окошек при их максимальном количестве,
    # оставляем frame. Т.е. на случай, если окошки не делят изображения нацело
    frame_shape = [count_of_center_points_x*window_size,
                   count_of_center_points_y*window_size]
    mask_frame = np.zeros(frame_shape, dtype=int)

    for x in np.arange(count_of_center_points_x) + 0.5:
        for y in np.arange(count_of_center_points_y) + 0.5:
            center_coords = np.ceil(np.asarray([x, y]) * window_size).astype(int)
            img2d_gray_frag = crop(img2d_gray, (window_size, window_size), center_coords)

            img2d_gray_frag = median(img2d_gray_frag)

            min_brightness = np.min(img2d_gray_frag)
            max_brightness = np.max(img2d_gray_frag)

            local_thresh = (min_brightness + max_brightness) * 0.5
            if local_thresh < global_thresh:
                local_thresh = global_thresh

            bin_cropped_fragment = img2d_gray_frag < local_thresh
            paste(mask_frame, bin_cropped_fragment, center_coords)
    
    mask_frame = binary_fill_holes(np.abs(mask_frame-1))

    check_mask = find_big_ones_clusters(mask_frame, min_large_contour_length)
    while np.any(check_mask):
        mask_frame = hide_image_elements(mask_frame, check_mask)
        check_mask = find_big_ones_clusters(mask_frame, min_large_contour_length)
        print("deleting remnants")

    return mask_frame.astype(bool)


if __name__=='__main__':
    thresh = lambda x: x>np.percentile(x.ravel(), 95)
    img2d = dm.get_img2d_from_database("reco_001000.tif")

    fig, axes = plt.subplots(ncols=2, nrows=2, figsize=(14, 14), constrained_layout=True)
    axes = axes.flatten()

    clip_limit = 0.1
    
    img2d_mask = thresh(exposure.equalize_adapthist(img2d, clip_limit=clip_limit))

    img2d_mask = get_small_pores_mask(img2d,
                                 img2d_mask,
                                 percentile_glob=97.5,
                                 min_large_contour_length=1000,
                                 window_size=200)


    squares = [([500, 1500], [600,1500]),
               ([900, 1200], [900,1200])]
    axes[0].imshow(img2d, cmap='gray')
    viewer.view_applied_rectangle(img2d, *squares[0], axes[0], color='red')
    viewer.view_applied_rectangle(img2d, *squares[1], axes[0], color='green')
    axes[0].set_title("original image")

    #axes[1].imshow(exposure.equalize_adapthist(img2d, clip_limit=0.05), cmap='gray')
    viewer.view_applied_mask(exposure.equalize_adapthist(img2d, clip_limit=clip_limit), img2d_mask, axes[1], alpha=1)
    viewer.view_applied_rectangle(img2d, *squares[0], axes[1], color='red')
    viewer.view_applied_rectangle(img2d, *squares[1], axes[1], color='green')
    axes[1].set_title("adaptive contrast")

    viewer.view_region(exposure.equalize_adapthist(img2d, clip_limit=clip_limit), img2d_mask, axes[2], *squares[0])
    axes[2].set_title("RED box zoomed", fontdict={'color': 'red'})

    viewer.view_region(img2d, img2d_mask, axes[3], *squares[1], alpha=0.3)
    axes[3].set_title("GREEN box zoomed", fontdict={'color': 'green'})
    
    dm.save_plot(fig, "plots", "section")

    # fig, axes = plt.subplots(ncols=2, figsize=(14, 7), constrained_layout=True)