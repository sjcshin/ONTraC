#!/usr/bin/env python

import os
import sys
from optparse import Values
from typing import Dict

import numpy as np
import yaml
from scipy.sparse import csr_matrix
from sklearn.neighbors import kneighbors_graph

from ONTraC.log import *
from ONTraC.optparser import (opt_create_ds_validate, prepare_create_ds_optparser)
from ONTraC.utils import read_yaml_file

# ------------------------------------
# Hyper-parameters
# ------------------------------------
self_path = os.path.dirname(os.path.abspath(__file__))
example_yaml_file = f'{self_path}/../example.yaml'


# ------------------------------------
# Classes
# ------------------------------------
class NoNameError(Exception):
    """
    No Name Error
    """

    def __init__(self, message='No Name Error'):
        self.message = message
        super().__init__(self.message)


class NoCoordinatesError(Exception):
    """
    No Coordinates Error
    """

    def __init__(self, message='No Coordinates Error'):
        self.message = message
        super().__init__(self.message)


class NoFeaturesError(Exception):
    """
    No Features Error
    """

    def __init__(self, message='No Features Error'):
        self.message = message
        super().__init__(self.message)


# ------------------------------------
# Functions
# ------------------------------------
def dataset_check(dataset: Dict) -> bool:
    """
    Check one dataset
    :param dataset: Dict, dataset
    :return: True if the dataset contains label, False otherwise
    """
    # Check Name
    if 'Name' not in dataset:
        raise NoNameError
    # Check Coordinates
    if 'Coordinates' not in dataset:
        raise NoCoordinatesError(f"{dataset['Name']} does not have coordinates file!")
    if not os.path.isfile(dataset['Coordinates']):
        raise FileNotFoundError(f"{dataset['Name']}'s coordinates file: {dataset['Coordinates']} does not exist!")
    # Check Features
    if 'Features' not in dataset:
        raise NoFeaturesError(f"{dataset['Name']} does not have features file!")
    if not os.path.isfile(dataset['Features']):
        raise FileNotFoundError(f"{dataset['Name']}'s features file: {dataset['Features']} does not exist!")
    # Check Label
    if 'Label' not in dataset:
        return False
    else:
        if not os.path.isfile(dataset['Label']):
            raise FileNotFoundError(f"{dataset['Name']}'s label file: {dataset['Label']} does not exist!")
        return True


def input_file_check(params: Dict) -> Dict:
    """
    Check input files
    :param params: parameters dictionary
    :return: None
    """
    total_datasets = len(params['Data'])
    valid_dataset = 0
    label_indicators = []
    filtered_params = {'Data': [], 'Label': False}
    for index, dataset in enumerate(params['Data']):
        try:
            label_indicator = dataset_check(dataset)
        except NoNameError:
            warning(f"Dataset {index+1} does not have Name!\nSkip this dataset!\n")
            continue
        except NoCoordinatesError:
            warning(f"Dataset {index+1} does not have Coordinates!\nSkip this dataset!\n")
            continue
        except NoFeaturesError:
            warning(f"Dataset {index+1} does not have Features!\nSkip this dataset!\n")
            continue
        except FileNotFoundError as e:
            warning(f"Dataset {index+1} has wrong file path!\n{e}\nSkip this dataset!\n")
            continue
        else:
            valid_dataset += 1
            label_indicators.append(label_indicator)
            filtered_params['Data'].append(dataset)

    # If have valid dataset
    if valid_dataset == 0:
        error('No valid dataset!')
        sys.exit(1)
    else:
        info(f'Valid datasets: {valid_dataset}/{total_datasets}')
    # If all datasets have labels
    if all(label_indicators):
        info('All datasets have labels!')
        filtered_params['Label'] = True
    else:
        info('Not all datasets have labels!')

    return filtered_params


def edge_definition(coordinates_file: str, edge_index_file: str, n_neighbors: int = 50) -> None:
    """
    Define edges
    :param coordinates_file: coordinates file path, csv format, no index.
    :param k: number of nearest neighbors
    :return: None

    Note: The edge index file will be saved in the same directory as the coordinates file.
    Edge index file format is csv, no header, no index, 2 columns, each row is an edge.
    """
    # Read coordinates
    if not os.path.isfile(coordinates_file):
        coordinates_file = f'{coordinates_file}.gz'
    coordinates = np.loadtxt(coordinates_file, delimiter=',')
    # Define edges
    adj_matrix: csr_matrix = kneighbors_graph(X=coordinates,
                                              n_neighbors=n_neighbors,
                                              mode='connectivity',
                                              include_self=False,
                                              n_jobs=-1)  # type: ignore
    adj_matrix = adj_matrix + adj_matrix.transpose()
    edge_index = np.argwhere(adj_matrix.todense() > 0)
    # Save edge index file
    np.savetxt(edge_index_file, edge_index, delimiter=',', fmt='%d')


def create_dataset(options: Values, params: Dict) -> None:
    """
    Create dataset
    :param params: parameters dictionary
    :return: None
    """
    input_files = ['Coordinates', 'Features']
    if params['Label']:
        input_files.append('Label')

    for dataset in params['Data']:
        # Create symbolic links
        for input_file in input_files:
            base_name = os.path.basename(dataset[input_file])
            os.symlink(f'{os.path.relpath(dataset[input_file],options.output)}', f'{options.output}/{base_name}')
        # Create edge index file
        edge_index_file = f'{options.output}/{dataset["Name"]}_edge_index.csv.gz'
        edge_definition(coordinates_file=dataset['Coordinates'],
                        edge_index_file=edge_index_file,
                        n_neighbors=options.n_neighbors)
        dataset['EdgeIndex'] = edge_index_file


# ------------------------------------
# Main Function
# ------------------------------------
def main() -> None:
    """
    main function
    Input data files information should be stored in a YAML file.
    """

    # load parameters
    options = opt_create_ds_validate(prepare_create_ds_optparser())
    params = read_yaml_file(options.yaml)

    # check input files
    filtered_params = input_file_check(params)

    # check output directory
    os.makedirs(options.output, exist_ok=True)

    # create dataset
    create_dataset(options, filtered_params)

    # save samples.yaml
    yaml_file = f'{options.output}/samples.yaml'
    for data in filtered_params['Data']:
        for k, v in data.items():
            if k != 'Name':
                data[k] = os.path.basename(v)
    with open(yaml_file, 'w') as fhd:
        yaml.dump(filtered_params, fhd)

    meta_file = example_yaml_file.split('/', 1)[0] + '/meta.csv'
    if os.path.exists(meta_file):
        os.symlink(meta_file, f'{options.output}/meta.csv')


# ------------------------------------
# Program running
# ------------------------------------
if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.stderr.write("User interrupts me! ;-) See you ^.^!\n")
        sys.exit(0)
