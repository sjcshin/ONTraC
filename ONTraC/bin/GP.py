#!/usr/bin/env python

import gzip
import os
import random
import sys
from collections import defaultdict
from functools import partial
from typing import Optional, Tuple, Type

import numpy as np
import torch
from torch_geometric.loader import DenseDataLoader

from ONTraC.log import debug, info, warning
from ONTraC.model import GraphPooling
from ONTraC.optparser import opt_GP_validate, prepare_GP_optparser
from ONTraC.run.processes import *
from ONTraC.train import GPBatchTrain, SubBatchTrainProtocol
from ONTraC.train.inspect_funcs import loss_record

# ------------------------------------
# Classes
# ------------------------------------


# ------------------------------------
# Functions
# ------------------------------------
def get_inspect_funcs() -> Optional[list[Callable]]:
    """
    Inspect function list
    :param output_dir: output dir
    :param epoch_filter: epoch filter
    :return: list of inspect functions
    """
    return [loss_record]


# ------------------------------------
# Main Function
# ------------------------------------
def main() -> None:
    """
    Main function
    :return: None
    """

    # ----- prepare -----
    # --- load parameters ---
    options, rel_params = load_parameters(opt_validate_func=opt_GP_validate,
                                          prepare_optparser_func=prepare_GP_optparser)
    # --- load data ---
    dataset, sample_loader = load_data(options=options, rel_params=rel_params)
    # --- prepare ---
    device: torch.device = tain_prepare(options=options)
    # --- random seed ---
    n_seed = t_seed = r_seed = options.seed
    random.seed(a=r_seed)
    torch.manual_seed(seed=t_seed)
    np.random.seed(seed=n_seed)

    # ----- train -----
    inspect_funcs_list = get_inspect_funcs()
    batch_train: SubBatchTrainProtocol = train(nn_model=GraphPooling,
                                                  options=options,
                                                  BatchTrain=GPBatchTrain,
                                                  device=device,
                                                  dataset=dataset,
                                                  sample_loader=sample_loader,
                                                  inspect_funcs=inspect_funcs_list,
                                                  model_name='GraphPooling')

    # --- evaluate ---
    evaluate(batch_train=batch_train, model_name='GraphPooling')

    # ----- predict -----
    consolidate_s_array, consolidate_out_adj_array = predict(output_dir=options.output,
                                                             batch_train=batch_train,
                                                             dataset=dataset,
                                                             model_name='GraphPooling')

    # ----- Pseudotime -----
    if consolidate_s_array is not None and consolidate_out_adj_array is not None:
        pseudotime(options=options,
                   dataset=dataset,
                   consolidate_s_array=consolidate_s_array,
                   consolidate_out_adj_array=consolidate_out_adj_array)


# ------------------------------------
# Program running
# ------------------------------------
if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.stderr.write("User interrupts me! ;-) See you ^.^!\n")
        sys.exit(0)
