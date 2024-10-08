from typing import List, Optional, Tuple, Union

import matplotlib as mpl
import networkx as nx
import numpy as np
import pandas as pd

mpl.rcParams['pdf.fonttype'] = 42
mpl.rcParams['ps.fonttype'] = 42
mpl.rcParams['font.family'] = 'Arial'

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, Normalize

from ..log import warning
from .data import AnaData
from .utils import gini, saptial_figsize


def _plot_niche_cluster_connectivity(
        niche_cluster_connectivity: np.ndarray,
        niche_cluster_score: np.ndarray,
        reverse: bool = False,
        output_file_path: Optional[str] = None) -> Optional[Tuple[plt.Figure, plt.Axes | List[plt.Axes]]]:
    """
    Plot niche cluster connectivity.
    :param niche_cluster_connectivity: np.ndarray, the connectivity matrix.
    :param niche_cluster_score: Optional[np.ndarray], the score of each niche cluster.
    :param reverse: bool, whether to reverse the color.
    :param output_file_path: Optional[str], the output file path.
    :return: None or Tuple[plt.Figure, plt.Axes].
    """

    G = nx.Graph(niche_cluster_connectivity / niche_cluster_connectivity.max())

    # position
    pos = nx.spring_layout(G, seed=42)
    # edges
    edges = G.edges()
    weights = [G[u][v]['weight'] for u, v in edges]
    # node color
    norm = Normalize(vmin=0, vmax=1)
    sm = ScalarMappable(cmap=plt.cm.rainbow, norm=norm)  # type: ignore
    nc_scores = 1 - niche_cluster_score if reverse else niche_cluster_score
    niche_cluster_colors = [sm.to_rgba(nc_scores[n]) for n in G.nodes]

    # Create a figure
    fig = plt.figure(figsize=(7, 6))

    # Create a gridspec with 1 row and 2 columns, with widths of A and B
    gs = gridspec.GridSpec(1, 2, width_ratios=[6, 1])  # 6:1 ratio
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])

    # Draw the graph
    nx.draw_networkx_nodes(G, pos, node_color=niche_cluster_colors, node_size=500, ax=ax1)
    nx.draw_networkx_edges(
        G,
        pos,
        edge_color=weights,
        alpha=weights,
        width=3.0,
        edge_cmap=plt.cm.Reds,  # type: ignore
        ax=ax1)
    nx.draw_networkx_labels(G, pos, ax=ax1)
    ax1.set_title('Niche cluster connectivity')

    # Draw the colorbar
    colors = [(1, 1, 1, 0), (1, 0, 0, 1)]
    custom_cmap = LinearSegmentedColormap.from_list('custom_cmap', colors)
    gradient = np.linspace(1, 0, 1000).reshape(-1, 1)
    ax2.imshow(gradient, aspect='auto', cmap=custom_cmap)
    ax2.set_xticks([])
    ax2.set_yticks(np.linspace(1000, 0, 5))
    ax2.set_yticklabels(f'{x:.2f}' for x in np.linspace(0, niche_cluster_connectivity.max(), 5))
    ax2.set_ylabel('Connectivity')

    fig.tight_layout()

    if output_file_path is not None:
        fig.savefig(output_file_path)
        return None
    else:
        return fig, [ax1, ax2]


def plot_niche_cluster_connectivity(ana_data: AnaData) -> Optional[Tuple[plt.Figure, plt.Axes | List[plt.Axes]]]:
    """
    Plot niche cluster connectivity.
    :param ana_data: AnaData, the data for analysis.
    :return: None or Tuple[plt.Figure, plt.Axes].
    """
    try:
        if ana_data.niche_cluster_score is None or ana_data.niche_cluster_connectivity is None:
            warning("No niche cluster score or connectivity data found.")
            return None
    except FileNotFoundError as e:
        warning(str(e))
        return None

    output_file_path = f'{ana_data.options.output}/niche_cluster_connectivity.pdf' if ana_data.options.output is not None else None
    return _plot_niche_cluster_connectivity(niche_cluster_connectivity=ana_data.niche_cluster_connectivity,
                                            niche_cluster_score=ana_data.niche_cluster_score,
                                            reverse=ana_data.options.reverse,
                                            output_file_path=output_file_path)


def plot_niche_cluster_connectivity_bysample(ana_data: AnaData) -> None:
    """
    Plot niche cluster connectivity by sample.
    :param ana_data: AnaData, the data for analysis.
    :return: None or List[Tuple[plt.Figure, List[plt.Axes]]].
    """

    for sample in ana_data.cell_type_composition['sample'].unique():
        niche_cluster_connectivity = np.loadtxt(f'{ana_data.options.GNN_dir}/{sample}_out_adj.csv.gz', delimiter=',')
        output_file_path = f'{ana_data.options.output}/{sample}_cluster_connectivity.pdf'
        _plot_niche_cluster_connectivity(niche_cluster_connectivity=niche_cluster_connectivity,
                                         niche_cluster_score=ana_data.niche_cluster_score,
                                         reverse=ana_data.options.reverse,
                                         output_file_path=output_file_path)


def plot_cluster_proportion(ana_data: AnaData) -> Optional[Tuple[plt.Figure, plt.Axes]]:
    """
    Plot the proportion of each cluster.
    :param ana_data: AnaData, the data for analysis.
    :return: None or Tuple[plt.Figure, plt.Axes].
    """
    try:
        if ana_data.niche_cluster_score is None or ana_data.niche_level_niche_cluster_assign is None:
            warning("No niche cluster score or connectivity data found.")
            return None
    except FileNotFoundError as e:
        warning(str(e))
        return None

    # colors
    norm = Normalize(vmin=0, vmax=1)
    sm = ScalarMappable(cmap=plt.cm.rainbow, norm=norm)  # type: ignore
    nc_scores = 1 - ana_data.niche_cluster_score if ana_data.options.reverse else ana_data.niche_cluster_score
    niche_cluster_colors = [sm.to_rgba(nc_scores[n]) for n in np.arange(ana_data.niche_cluster_score.shape[0])]

    # loadings
    niche_cluster_loading = ana_data.niche_level_niche_cluster_assign.sum(axis=0)

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(niche_cluster_loading,
           labels=[f'Niche cluster {i}' for i in range(niche_cluster_loading.shape[0])],
           colors=niche_cluster_colors,
           autopct='%1.1f%%',
           pctdistance=1.25,
           labeldistance=.6)
    ax.set_title(f'Niche proportions for each niche cluster')
    fig.tight_layout()
    if ana_data.options.output is not None:
        fig.savefig(f'{ana_data.options.output}/niche_cluster_proportion.pdf')
        return None
    else:
        return fig, ax


def plot_niche_cluster_loadings_dataset(ana_data: AnaData) -> Optional[Tuple[plt.Figure, plt.Axes]]:
    """
    Plot niche cluster loadings for each cell.
    :param ana_data: AnaData, the data for analysis.
    :return: None or Tuple[plt.Figure, plt.Axes].
    """

    try:
        if ana_data.niche_cluster_score is None or ana_data.cell_type_composition is None or ana_data.cell_level_niche_cluster_assign is None:
            warning("No niche cluster score, cell type composition or cluster assign data found.")
            return None
    except FileNotFoundError as e:
        warning(str(e))
        return None

    nc_scores = 1 - ana_data.niche_cluster_score if ana_data.options.reverse else ana_data.niche_cluster_score
    samples: List[str] = ana_data.cell_type_composition['sample'].unique().tolist()
    M, N = len(samples), ana_data.cell_level_niche_cluster_assign.shape[1]

    fig, axes = plt.subplots(M, N, figsize=(3.3 * N, 3 * M))
    for i, sample in enumerate(samples):
        sample_df = ana_data.cell_level_niche_cluster_assign.loc[ana_data.cell_type_composition[
            ana_data.cell_type_composition['sample'] == sample].index]
        sample_df = sample_df.join(ana_data.cell_type_composition[['x', 'y']])
        for j, c_index in enumerate(nc_scores.argsort()):
            ax = axes[i, j] if M > 1 else axes[j]
            scatter = ax.scatter(sample_df['x'],
                                 sample_df['y'],
                                 c=sample_df[f'NicheCluster_{c_index}'],
                                 cmap='Reds',
                                 vmin=0,
                                 vmax=1,
                                 s=4)
            ax.set_title(f'{sample}: niche cluster {c_index}')
            plt.colorbar(scatter)
    fig.tight_layout()
    if ana_data.options.output is not None:
        fig.savefig(f'{ana_data.options.output}/niche_cluster_loadings.pdf')
        return None
    else:
        return fig, ax


def plot_niche_cluster_loadings_sample(ana_data: AnaData) -> Optional[List[Tuple[plt.Figure, plt.Axes]]]:
    """
    Plot niche cluster loadings for each cell.
    :param ana_data: AnaData, the data for analysis.
    :return: None or List[Tuple[plt.Figure, plt.Axes]].
    """

    try:
        if ana_data.niche_cluster_score is None or ana_data.cell_type_composition is None or ana_data.cell_level_niche_cluster_assign is None:
            warning("No niche cluster score, cell type composition or cluster assign data found.")
            return None
    except FileNotFoundError as e:
        warning(str(e))
        return None

    nc_scores = 1 - ana_data.niche_cluster_score if ana_data.options.reverse else ana_data.niche_cluster_score
    samples: List[str] = ana_data.cell_type_composition['sample'].unique().tolist()

    output = []
    for sample in samples:
        sample_df = ana_data.cell_level_niche_cluster_assign.loc[ana_data.cell_type_composition[
            ana_data.cell_type_composition['sample'] == sample].index]
        sample_df = sample_df.join(ana_data.cell_type_composition[['x', 'y']])
        fig_width, fig_height = saptial_figsize(sample_df, scale_factor=ana_data.options.scale_factor)
        fig, axes = plt.subplots(1, nc_scores.shape[0], figsize=(fig_width * nc_scores.shape[0], fig_height))
        for j, c_index in enumerate(nc_scores.argsort()):
            ax = axes[j]  #  there should more than one niche cluster
            scatter = ax.scatter(sample_df['x'],
                                 sample_df['y'],
                                 c=sample_df[f'NicheCluster_{c_index}'],
                                 cmap='Reds',
                                 vmin=0,
                                 vmax=1,
                                 s=4)
            ax.set_title(f'{sample}: niche cluster {c_index}')
            plt.colorbar(scatter)
        fig.tight_layout()
        output.append((fig, axes))
        if ana_data.options.output is not None:
            fig.savefig(f'{ana_data.options.output}/niche_cluster_loadings_{sample}.pdf')
    return output if len(output) > 0 else None


def plot_niche_cluster_loadings(
        ana_data: AnaData) -> Optional[Union[List[Tuple[plt.Figure, plt.Axes]], Tuple[plt.Figure, plt.Axes]]]:
    """
    Plot niche cluster loadings for each cell.
    :param ana_data: AnaData, the data for analysis.
    :return: None or Tuple[plt.Figure, plt.Axes].
    """
    if hasattr(ana_data.options, 'sample') and ana_data.options.sample:
        return plot_niche_cluster_loadings_sample(ana_data=ana_data)
    else:
        return plot_niche_cluster_loadings_dataset(ana_data=ana_data)


def plot_max_niche_cluster_dataset(ana_data: AnaData) -> Optional[Tuple[plt.Figure, plt.Axes]]:
    """
    Plot the maximum niche cluster for each cell.
    :param ana_data: AnaData, the data for analysis.
    :return: None or Tuple[plt.Figure, plt.Axes].
    """

    try:
        if ana_data.niche_cluster_score is None or ana_data.cell_type_composition is None or ana_data.cell_level_max_niche_cluster is None:
            warning("No niche cluster score, cell type composition or max niche cluster data found.")
            return None
    except FileNotFoundError as e:
        warning(str(e))
        return None

    # colors
    norm = Normalize(vmin=0, vmax=1)
    sm = ScalarMappable(cmap=plt.cm.rainbow, norm=norm)  # type: ignore
    nc_scores = 1 - ana_data.niche_cluster_score if ana_data.options.reverse else ana_data.niche_cluster_score
    niche_cluster_colors = [sm.to_rgba(nc_scores[n]) for n in np.arange(ana_data.niche_cluster_score.shape[0])]
    palette = {f'niche cluster {i}': niche_cluster_colors[i] for i in range(ana_data.niche_cluster_score.shape[0])}
    samples: List[str] = ana_data.cell_type_composition['sample'].unique().tolist()
    M = len(samples)

    fig, axes = plt.subplots(1, M, figsize=(5 * M, 3))
    for i, sample in enumerate(samples):
        ax = axes[i] if M > 1 else axes
        sample_df = ana_data.cell_level_max_niche_cluster.loc[ana_data.cell_type_composition[
            ana_data.cell_type_composition['sample'] == sample].index]
        sample_df = sample_df.join(ana_data.cell_type_composition[['x', 'y']])
        sample_df['Niche_Cluster'] = 'niche cluster ' + sample_df['Niche_Cluster'].astype(str)
        sns.scatterplot(data=sample_df,
                        x='x',
                        y='y',
                        hue='Niche_Cluster',
                        hue_order=[f'niche cluster {j}' for j in nc_scores.argsort()],
                        palette=palette,
                        s=10,
                        ax=ax)
        ax.set_title(f'{sample}')
        ax.legend(loc='upper left', bbox_to_anchor=(1, 1))
    fig.tight_layout()
    if ana_data.options.output is not None:
        fig.savefig(f'{ana_data.options.output}/max_niche_cluster.pdf')
        return None
    else:
        return fig, axes


def plot_max_niche_cluster_sample(ana_data: AnaData) -> Optional[List[Tuple[plt.Figure, plt.Axes]]]:
    """
    Plot the maximum niche cluster for each cell.
    :param ana_data: AnaData, the data for analysis.
    :return: None or List[Tuple[plt.Figure, plt.Axes]].
    """

    try:
        if ana_data.niche_cluster_score is None or ana_data.cell_type_composition is None or ana_data.cell_level_max_niche_cluster is None:
            warning("No niche cluster score, cell type composition or max niche cluster data found.")
            return None
    except FileNotFoundError as e:
        warning(str(e))
        return None

    # colors
    norm = Normalize(vmin=0, vmax=1)
    sm = ScalarMappable(cmap=plt.cm.rainbow, norm=norm)  # type: ignore
    nc_scores = 1 - ana_data.niche_cluster_score if ana_data.options.reverse else ana_data.niche_cluster_score
    niche_cluster_colors = [sm.to_rgba(nc_scores[n]) for n in np.arange(ana_data.niche_cluster_score.shape[0])]
    palette = {f'niche cluster {i}': niche_cluster_colors[i] for i in range(ana_data.niche_cluster_score.shape[0])}
    samples: List[str] = ana_data.cell_type_composition['sample'].unique().tolist()

    output = []
    for sample in samples:
        sample_df = ana_data.cell_level_max_niche_cluster.loc[ana_data.cell_type_composition[
            ana_data.cell_type_composition['sample'] == sample].index]
        sample_df = sample_df.join(ana_data.cell_type_composition[['x', 'y']])
        sample_df['Niche_Cluster'] = 'niche cluster ' + sample_df['Niche_Cluster'].astype(str)
        fig_width, fig_height = saptial_figsize(sample_df, scale_factor=ana_data.options.scale_factor)
        fig, ax = plt.subplots(1, 1, figsize=(fig_width, fig_height))
        sns.scatterplot(data=sample_df,
                        x='x',
                        y='y',
                        hue='Niche_Cluster',
                        hue_order=[f'niche cluster {j}' for j in nc_scores.argsort()],
                        palette=palette,
                        s=10,
                        ax=ax)
        ax.set_title(f'{sample}')
        ax.legend(loc='upper left', bbox_to_anchor=(1, 1))
        fig.tight_layout()
        output.append((fig, ax))
        if ana_data.options.output is not None:
            fig.savefig(f'{ana_data.options.output}/max_niche_cluster_{sample}.pdf')
    return output if len(output) > 0 else None


def plot_max_niche_cluster(
        ana_data: AnaData) -> Optional[Union[List[Tuple[plt.Figure, plt.Axes]], Tuple[plt.Figure, plt.Axes]]]:
    """
    Plot the maximum niche cluster for each cell.
    :param ana_data: AnaData, the data for analysis.
    :return: None or Tuple[plt.Figure, plt.Axes].
    """
    if hasattr(ana_data.options, 'sample') and ana_data.options.sample:
        return plot_max_niche_cluster_sample(ana_data=ana_data)
    else:
        return plot_max_niche_cluster_dataset(ana_data=ana_data)


def plot_niche_cluster_gini(ana_data: AnaData) -> Optional[Tuple[plt.Figure, plt.Axes]]:
    """
    Plot the Gini coefficient of each niche cluster.
    :param ana_data: AnaData, the data for analysis.
    :return: None or Tuple[plt.Figure, plt.Axes].
    """
    try:
        if ana_data.cell_level_niche_cluster_assign is None:
            warning("No niche cluster assign data found.")
            return None
    except FileNotFoundError as e:
        warning(str(e))
        return None
    intra_cluster_gini = ana_data.cell_level_niche_cluster_assign.apply(gini, axis=0).values
    intra_cluster_gini_df = pd.DataFrame(data={
        'gini': intra_cluster_gini,
        'cluster': ana_data.cell_level_niche_cluster_assign.columns
    })
    fig, ax = plt.subplots(figsize=(6, 4))
    sns.barplot(data=intra_cluster_gini_df, x='cluster', y='gini', ax=ax)
    ax.set_xlabel('Niche Cluster')
    ax.set_ylabel('Gini coefficient across each cell')
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45, horizontalalignment='right')
    fig.tight_layout()
    if ana_data.options.output is not None:
        fig.savefig(f'{ana_data.options.output}/niche_cluster_gini.pdf')
        return None
    else:
        return fig, ax


def niche_cluster_visualization(ana_data: AnaData) -> None:
    """
    All spatial visualization will include here.
    :param ana_data: AnaData, the data for analysis.
    :return: None.
    """

    # 1. plot niche cluster connectivity
    plot_niche_cluster_connectivity(ana_data=ana_data)

    if hasattr(ana_data.options, 'sample') and ana_data.options.sample:
        plot_niche_cluster_connectivity_bysample(ana_data=ana_data)

    # 2. share of each cluster
    plot_cluster_proportion(ana_data=ana_data)

    # 3. niche cluster loadings for each cell
    if not hasattr(ana_data.options,
                   'suppress_niche_cluster_loadings') or not ana_data.options.suppress_niche_cluster_loadings:
        plot_niche_cluster_loadings(ana_data=ana_data)

    # 4. maximum niche cluster for each cell
    plot_max_niche_cluster(ana_data=ana_data)

    # 5. gini coefficient of each niche cluster
    plot_niche_cluster_gini(ana_data=ana_data)
