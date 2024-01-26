from optparse import Values
from typing import Dict, List

import numpy as np
import torch
import torch_geometric.transforms as T
from torch_geometric.data import Data, InMemoryDataset

from .log import *
from .utils import count_lines


# ------------------------------------
# Classes
# ------------------------------------
class SpatailOmicsDataset(InMemoryDataset):

    def __init__(self, root, params: Dict, transform=None, pre_transform=None):
        self.params = params
        super(SpatailOmicsDataset, self).__init__(root, transform, pre_transform)
        self.data, self.slices = torch.load(self.processed_paths[0])

    @property
    def raw_file_names(self):
        # return list(
        #     flatten([[sample for name, sample in data.items() if name != 'Name'] for data in self.params['Data']]))
        return []

    @property
    def processed_file_names(self):
        return ['data.pt']

    def download(self):
        pass

    def process(self):
        data_list = []
        for index, sample in enumerate(self.params['Data']):
            info(f'Processing sample {index + 1} of {len(self.params["Data"])}')
            if self.params['Label']:
                data = Data(x=torch.from_numpy(np.loadtxt(sample['Features'], dtype=np.float32, delimiter=',')),
                            y=torch.from_numpy(np.loadtxt(sample['Label'], dtype=np.int8, delimiter=',')),
                            edge_index=torch.from_numpy(np.loadtxt(sample['EdgeIndex'], dtype=np.int64,
                                                                   delimiter=',')).t().contiguous(),
                            pos=torch.from_numpy(np.loadtxt(sample['Coordinates'], dtype=np.float32, delimiter=',')),
                            name=sample['Name'])
            else:
                data = Data(x=torch.from_numpy(np.loadtxt(sample['Features'], dtype=np.float32, delimiter=',')),
                            edge_index=torch.from_numpy(np.loadtxt(sample['EdgeIndex'], dtype=np.int64,
                                                                   delimiter=',')).t().contiguous(),
                            pos=torch.from_numpy(np.loadtxt(sample['Coordinates'], dtype=np.float32, delimiter=',')),
                            name=sample['Name'])
            data_list.append(data)
        data, slices = self.collate(data_list)
        torch.save((data, slices), self.processed_paths[0])


# ------------------------------------
# Misc functions
# ------------------------------------
def max_nodes(samples: List[Dict[str, str]]) -> int:
    """
    Get the maximum number of nodes in a dataset
    :param params: List[Dict[str, str], list of samples
    :return: int, maximum number of nodes
    """
    max_nodes = 0
    for sample in samples:
        max_nodes = max(max_nodes, count_lines(sample['Coordinates']))
    return max_nodes


# ------------------------------------
# Flow control functions
# ------------------------------------
def create_torch_dataset(options: Values, params: Dict) -> SpatailOmicsDataset:
    """
    Create torch dataset
    :param params: Dict, input samples
    :return: None
    """

    # ------------------------------------
    # Step 1: Get the maximum number of nodes
    m_nodes = max_nodes(params['Data'])
    # upcelling m_nodes to the nearest 100
    m_nodes = int(np.ceil(m_nodes / 100.0)) * 100
    info(f'Maximum number of nodes: {m_nodes}')
    # ------------------------------------

    # ------------------------------------
    # Step 2: Create torch dataset
    dataset = SpatailOmicsDataset(root=options.input, params=params, transform=T.ToDense(m_nodes))  # transform edge_index to adj matrix
    # dataset = SpatailOmicsDataset(root=options.input, params=params)
    return dataset