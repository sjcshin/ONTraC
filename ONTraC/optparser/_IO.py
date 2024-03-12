import os
import sys
from optparse import OptionGroup, OptionParser, Values
from typing import List, Optional

from ..log import *


def add_IO_options_group(optparser: OptionParser, io_options: Optional[List[str]]) -> None:
    """
    Add I/O options group to optparser.
    :param optparser: OptionParser object.
    :return: OptionGroup object.
    """
    if io_options is None:
        return
    # I/O options group
    group_io = OptionGroup(optparser, "IO")
    if 'dataset' in io_options:
        group_io.add_option('-d', '--dataset', dest='dataset', type='string', help='Original input dataset.')
    if 'preprocessing_dir' in io_options:
        group_io.add_option('--preprocessing-dir',
                            dest='preprocessing_dir',
                            type='string',
                            help='Directory for preprocessing outputs.')
    if 'GNN_dir' in io_options:
        group_io.add_option('--GNN-dir', dest='GNN_dir', type='string', help='Directory for the GNN output.')
    if 'NTScore_dir' in io_options:
        group_io.add_option('--NTScore-dir', dest='NTScore_dir', type='string', help='Directory for the NTScore output')

    optparser.add_option_group(group_io)


def validate_io_options(optparser: OptionParser, options: Values, io_options: Optional[List[str]]) -> None:
    """Validate IO options from a OptParser object.

    Ret: None
    """
    if io_options is None:
        return
    if 'dataset' in io_options:
        if not options.dataset:
            error('Please provide a dataset.')
            optparser.print_help()
            sys.exit(1)
        if not os.path.isfile(options.dataset):
            error(f'The input file ({options.dataset}) you given does not exist.')
            optparser.print_help()
            sys.exit(1)
        if options.dataset.endswith(('csv', 'csv.gz')):
            error('The input file should be in csv format.')
            optparser.print_help()
            sys.exit(1)

    if 'preprocessing_dir' in io_options:
        if not options.preprocessing_dir:
            error('Please provide a directory for preprocessing outputs.')
            optparser.print_help()
            sys.exit(1)

    if 'GNN_dir' in io_options:
        if not options.GNN_dir:
            error('Please provide a directory for the GNN output.')
            optparser.print_help()
            sys.exit(1)

    if 'NTScore_dir' in io_options:
        if not options.NTScore_dir:
            error('Please provide a directory for the NTScore output.')
            optparser.print_help()
            sys.exit(1)


def write_io_options_memo(options: Values) -> None:
    """Write IO options to stdout.

    Ret: None
    """
    info('            -------- I/O options -------             ')
    if options.preprocessing_dir:
        info(f'preprocessing output directory:  {options.preprocessing_dir}')
    if options.GNN_dir:
        info(f'GNN output directory:  {options.GNN_dir}')
    if options.NTScore_dir:
        info(f'NTScore output directory:  {options.NTScore_dir}')
    if options.dataset:
        info(f'dataset: {options.dataset}')
