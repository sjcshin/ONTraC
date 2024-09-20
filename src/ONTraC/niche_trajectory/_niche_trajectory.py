import itertools
import os
from optparse import Values
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from numpy import ndarray
from scipy.sparse import load_npz

from ..data import SpatailOmicsDataset
from ..log import error, info


def load_consolidate_data(options: Values) -> Tuple[ndarray, ndarray]:
    """
    Load consolidate s_array and out_adj_array
    :param options: Values, options
    :return: Tuple[ndarray, ndarray], the consolidate s_array and out_adj_array
    """

    info('Loading consolidate s_array and out_adj_array...')

    if not os.path.exists(f'{options.GNN_dir}/consolidate_s.csv.gz') or not os.path.exists(
            f'{options.GNN_dir}/consolidate_out_adj.csv.gz'):
        error(f'consolidate_s.csv.gz or consolidate_out_adj.csv.gz does not exist in {options.GNN_dir} directory.')
    consolidate_s_array = np.loadtxt(fname=f'{options.GNN_dir}/consolidate_s.csv.gz', delimiter=',')
    consolidate_out_adj_array = np.loadtxt(fname=f'{options.GNN_dir}/consolidate_out_adj.csv.gz', delimiter=',')

    return consolidate_s_array, consolidate_out_adj_array


def get_niche_trajectory_path(options: Values, niche_adj_matrix: ndarray) -> List[int]:
    """
    Find niche level trajectory with maximum connectivity using Brute Force
    :param adj_matrix: non-negative ndarray, adjacency matrix of the graph
    :return: List[int], the niche trajectory
    """

    if options.trajectory_construct == 'BF':
        info('Finding niche trajectory with maximum connectivity using Brute Force.')

        max_connectivity = float('-inf')
        niche_trajectory_path = []
        for path in itertools.permutations(range(len(niche_adj_matrix))):
            connectivity = 0
            for i in range(len(path) - 1):
                connectivity += niche_adj_matrix[path[i], path[i + 1]]
            if connectivity > max_connectivity:
                max_connectivity = connectivity
                niche_trajectory_path = list(path)

    elif options.trajectory_construct == 'TSP':
        info('Finding niche trajectory with maximum connectivity using TSP.')

        n = len(niche_adj_matrix)
        C = {}

        # Initial state
        for k in range(1, n):
            C[(1 << k, k)] = (niche_adj_matrix[0][k], [0, k])

        # Iterate subsets of increasing length and store the maximum path
        for subset_size in range(2, n):
            for subset in itertools.combinations(range(1, n), subset_size):
                bits = 0
                for bit in subset:
                    bits |= 1 << bit

                for k in subset:
                    prev_bits = bits & ~(1 << k)
                    res = []
                    for m in subset:
                        if m == k:
                            continue
                        res.append((C[(prev_bits, m)][0] + niche_adj_matrix[m][k], C[(prev_bits, m)][1] + [k]))
                    C[(bits, k)] = max(res)

        # We're interested in all bits but the least significant (the start city)
        bits = (2**n - 1) - 1

        res = []
        for k in range(1, n):
            res.append((C[(bits, k)][0] + niche_adj_matrix[k][0], C[(bits, k)][1]))

        max_cost, niche_trajectory_path = max(res)
        niche_trajectory_path.append(0)  # complete the cycle

        # Cut the shortest edge out from the cycle
        dists = []
        for i in range(len(niche_trajectory_path) - 1):
            dists.append(niche_adj_matrix[niche_trajectory_path[i]][niche_trajectory_path[i + 1]])

        cut_index = dists.index(min(dists))
        if niche_trajectory_path[cut_index] < niche_trajectory_path[cut_index + 1]:
            start_index = cut_index
            end_index = cut_index + 1
        else:
            start_index = cut_index + 1
            end_index = cut_index

        if start_index == len(niche_trajectory_path) - 1:
            niche_trajectory_path.pop(start_index)
        elif start_index == 0:
            niche_trajectory_path.pop(start_index)
            niche_trajectory_path.reverse()
        elif start_index < end_index:
            niche_trajectory_path.pop(len(path) - 1)
            seg1 = niche_trajectory_path[:start_index + 1]
            seg1.reverse()
            seg2 = niche_trajectory_path[end_index:]
            seg2.reverse()
            niche_trajectory_path = seg1 + seg2
        else:
            niche_trajectory_path.pop(len(niche_trajectory_path) - 1)
            seg1 = niche_trajectory_path[start_index:]
            seg2 = niche_trajectory_path[:end_index + 1]
            niche_trajectory_path = seg1 + seg2

    return niche_trajectory_path


def trajectory_path_to_NC_score(niche_trajectory_path: List[int]) -> ndarray:
    """
    Convert niche cluster trajectory path to NTScore
    :param niche_trajectory_path: List[int], the niche trajectory path
    :return: ndarray, the NTScore
    """

    info('Calculating NTScore for each niche cluster based on the trajectory path.')

    niche_NT_score = np.zeros(len(niche_trajectory_path))
    values = np.linspace(0, 1, len(niche_trajectory_path))

    for i, index in enumerate(niche_trajectory_path):
        # debug(f'i: {i}, index: {index}')
        niche_NT_score[index] = values[i]
    return niche_NT_score


def get_niche_NTScore(options: Values, niche_cluster_loading: ndarray,
                      niche_adj_matrix: ndarray) -> Tuple[ndarray, ndarray]:
    """
    Get niche-level niche trajectory and cell-level niche trajectory
    :param niche_cluster_loading: ndarray, the loading of cell x niche clusters
    :param adj_matrix: ndarray, the adjacency matrix of the graph
    :return: Tuple[ndarray, ndarray], the niche-level niche trajectory and cell-level niche trajectory
    """

    info('Calculating NTScore for each niche.')

    niche_trajectory_path = get_niche_trajectory_path(options=options, niche_adj_matrix=niche_adj_matrix)

    niche_cluster_score = trajectory_path_to_NC_score(niche_trajectory_path)
    niche_level_NTScore = niche_cluster_loading @ niche_cluster_score
    return niche_cluster_score, niche_level_NTScore


def niche_to_cell_NTScore(dataset: SpatailOmicsDataset, rel_params: Dict,
                          niche_level_NTScore: ndarray) -> Tuple[ndarray, Dict[str, ndarray], Dict[str, ndarray]]:
    """
    get cell-level NTScore
    :param dataset: SpatailOmicsDataset, dataset
    :param rel_params: Dict, relative paths
    :param niche_level_NTScore: ndarray, niche-level NTScore
    :return: Tuple[ndarray, Dict[str, ndarray], Dict[str, ndarray]], the cell-level NTScore, all niche-level NTScore dict,
    and all cell-level NTScore dict
    """

    info('Projecting NTScore from niche-level to cell-level.')

    cell_level_NTScore = np.zeros(niche_level_NTScore.shape[0])

    all_niche_level_NTScore_dict: Dict[str, ndarray] = {}
    all_cell_level_NTScore_dict: Dict[str, ndarray] = {}

    for i, data in enumerate(dataset):
        # the slice of data in each sample
        mask = data.mask
        slice_ = slice(i * data.x.shape[0], i * data.x.shape[0] + mask.sum())

        # niche to cell matrix
        niche_weight_matrix = load_npz(rel_params['Data'][i]['NicheWeightMatrix'])
        niche_to_cell_matrix = (
            niche_weight_matrix /
            niche_weight_matrix.sum(axis=0)).T  # normalize by the all niches associated with each cell, N x N

        # cell-level NTScore
        niche_level_NTScore_ = niche_level_NTScore[slice_].reshape(-1, 1)  # N x 1
        cell_level_NTScore_ = niche_to_cell_matrix @ niche_level_NTScore_
        cell_level_NTScore[slice_] = cell_level_NTScore_.reshape(-1)

        all_niche_level_NTScore_dict[data.name] = niche_level_NTScore_
        all_cell_level_NTScore_dict[data.name] = cell_level_NTScore_

    return cell_level_NTScore, all_niche_level_NTScore_dict, all_cell_level_NTScore_dict


def NTScore_table(options: Values, rel_params: Dict, all_niche_level_NTScore_dict: Dict[str, ndarray],
                  all_cell_level_NTScore_dict: Dict[str, ndarray]) -> None:
    """
    Generate NTScore table and save it
    :param options: Values, options
    :param rel_params: Dict, relative paths
    :param all_niche_level_NTScore_dict: Dict[str, ndarray], all niche-level NTScore dict
    :param all_cell_level_NTScore_dict: Dict[str, ndarray], all cell-level NTScore dict
    :return: pd.DataFrame, NTScore table
    """

    info('Output NTScore tables.')

    NTScore_table = pd.DataFrame()
    for sample in rel_params['Data']:
        coordinates_df = pd.read_csv(sample['Coordinates'], index_col=0)
        coordinates_df['Niche_NTScore'] = all_niche_level_NTScore_dict[sample['Name']]
        coordinates_df['Cell_NTScore'] = all_cell_level_NTScore_dict[sample['Name']]
        coordinates_df.to_csv(f'{options.NTScore_dir}/{sample["Name"]}_NTScore.csv.gz')
        NTScore_table = pd.concat([NTScore_table, coordinates_df])

    NTScore_table.to_csv(f'{options.NTScore_dir}/NTScore.csv.gz')
