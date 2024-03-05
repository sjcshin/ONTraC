import re
from abc import ABC, abstractmethod
from optparse import Values
from typing import Callable, Dict, List, Optional, Protocol, Tuple

import numpy as np
import torch
from torch import Tensor
from torch_geometric.data import Data
from torch_geometric.loader import DataLoader

from ONTraC.utils.decorators import selective_args_decorator

from ..log import debug
from ..utils.decorators import selective_args_decorator
from .loss_funs import (binary_pooling_loss, graph_smooth_loss, masked_variance, recon_loss,
                        within_cluster_variance_loss)
from ..utils import round_epoch_filter


class BatchTrain(ABC):
    """docstring for BatchTrain"""

    def __init__(self, model: torch.nn.Module, device: torch.device, data_loader: DataLoader) -> None:
        super(BatchTrain, self).__init__()
        self.model: torch.nn.Module = model
        self.device: torch.device = device
        self.data_loader: DataLoader = data_loader
        self.model = self.model.to(device=self.device)

    def __str__(self):
        return f"{self.__class__.__name__}(model='{self.model}', device='{self.device}', data_loader='{self.data_loader}')"

    def __repr__(self):
        return self.__str__()

    def train(self,
              max_epochs: int = 100,
              max_patience: int = 50,
              min_delta: float = 0,
              min_epochs: int = 100,
              *args,
              **kwargs) -> None:

        self.set_train_args(*args, **kwargs)

        self.model.train()
        min_loss = np.inf
        patience = 0
        best_params = self.model.state_dict()

        for epoch in range(max_epochs):
            train_loss = self.train_epoch(epoch=epoch)
            if np.isnan(train_loss):  # unexpected situation
                best_params = self.model.state_dict()
                break
            elif max_patience == 0:  # no early stopping
                best_params = self.model.state_dict()
            elif min_loss - train_loss < min_loss * min_delta:  # no improvement
                patience += 1
            else:  # improvement
                min_loss = train_loss
                patience = 0
                best_params = self.model.state_dict()
            # max_patience == 0 means no early stopping
            if max_patience != 0 and patience >= max_patience and epoch >= min_epochs:
                break
            if round_epoch_filter(epoch) and 'output' in kwargs:
                output_dir = kwargs['output']
                self.save(f'{output_dir}/epoch_{epoch + 1}.pt')
        self.model.load_state_dict(best_params)

    @abstractmethod
    def set_train_args(self) -> None:
        """Method that should be implemented by all derived classes."""
        raise NotImplementedError("The set_train_args method should be implemented by subclasses.")

    @abstractmethod
    def train_epoch(self, epoch: int) -> float:
        """Method that should be implemented by all derived classes."""
        raise NotImplementedError("The train_epoch method should be implemented by subclasses.")

    @abstractmethod
    def evaluate(self) -> Dict[str, np.floating]:
        """Method that should be implemented by all derived classes."""
        raise NotImplementedError("The evaluate method should be implemented by subclasses.")

    def predict(self, data: Data) -> Tuple[Tensor, ...] | Tensor:
        self.model.eval()
        with torch.no_grad():
            res = self.model.predict(data.x, data.adj, data.mask)  # type: ignore
        return res

    @abstractmethod
    def predict_dict(self, data: Data) -> Dict[str, Tensor]:
        """Method that should be implemented by all derived classes."""
        raise NotImplementedError("The predict_dict method should be implemented by subclasses.")

    def save(self, path: str) -> None:
        torch.save(self.model.state_dict(), path)

    def load(self, path: str) -> None:
        self.model.load_state_dict(torch.load(path))


class SubBatchTrainProtocol(Protocol):

    def train(self, *args, **kwargs) -> None:
        ...

    def evaluate(self) -> Dict[str, np.floating]:
        ...

    def predict(self, data: Data) -> Tuple[Tensor, ...] | Tensor:
        ...

    def predict_dict(self, data: Data) -> Dict[str, Tensor]:
        ...

    def save(self, path: str) -> None:
        ...

    def load(self, path: str) -> None:
        ...


class GSAEBatchTrain(BatchTrain):
    """
    GraphSAE batch training class.
    """

    def set_train_args(self,
                       optimizer: torch.optim.Optimizer,
                       recon_loss_weight: float = 1,
                       graph_smooth_loss_weight: float = 1,
                       inspect_funcs: Optional[List[Callable]] = None) -> None:
        self.recon_loss_weight = recon_loss_weight
        self.graph_smooth_loss_weight = graph_smooth_loss_weight
        self.optimizer = optimizer
        self.inspect_funcs = inspect_funcs

    def train_epoch(self, epoch: int) -> float:
        self.model.train()
        train_loss = 0
        for batch, data in enumerate(self.data_loader):
            # debug(f'epoch {epoch+1}, batch {batch+1} start.')
            data = data.to(self.device)
            recon_x, z = self.model(data.x, data.adj, data.mask)
            r_loss = recon_loss(x=data.x, recon_x=recon_x, mask=data.mask)
            g_loss = graph_smooth_loss(z=z, adj=data.adj, mask=data.mask)
            loss = self.recon_loss_weight * r_loss + self.graph_smooth_loss_weight * g_loss
            loss.backward()
            self.optimizer.step()
            self.optimizer.zero_grad()
            # debug(f'epoch {epoch+1}, batch {batch+1} end.')
            if self.inspect_funcs is not None:
                for inspect_func in self.inspect_funcs:
                    inspect_func(epoch=epoch + 1,
                                 batch=batch + 1,
                                 data=data,
                                 z=z,
                                 recon_x=recon_x,
                                 loss=loss,
                                 recon_loss=r_loss,
                                 graph_smooth_loss=g_loss)
            train_loss += loss.item()
        return train_loss

    def predict_recon(self, data: Data) -> Tensor:
        self.model.eval()
        with torch.no_grad():
            recon_x = self.model.predict_recon(data.x, data.adj, data.mask)  # type: ignore
        return recon_x


class NPBatchTrain(BatchTrain):
    """
    NodePooling batch training class.
    """

    def set_train_args(self,
                       optimizer: torch.optim.Optimizer,
                       spectral_loss_weight: float = 1,
                       ortho_loss_weight: float = 0,
                       cluster_loss_weight: float = 1,
                       bin_spectral_loss_weight: float = 0,
                       bin_ortho_loss_weight: float = 0,
                       bin_cluster_loss_weight: float = 0,
                       feat_similarity_loss_weight: float = 0,
                       inspect_funcs: Optional[List[Callable]] = None) -> None:
        self.optimizer = optimizer
        self.spectral_loss_weight = spectral_loss_weight
        self.ortho_loss_weight = ortho_loss_weight
        self.cluster_loss_weight = cluster_loss_weight
        self.bin_spectral_loss_weight = bin_spectral_loss_weight
        self.bin_ortho_loss_weight = bin_ortho_loss_weight
        self.bin_cluster_loss_weight = bin_cluster_loss_weight
        self.feat_similarity_loss_weight = feat_similarity_loss_weight
        self.inspect_funcs = inspect_funcs

    def train_epoch(self, epoch: int) -> float:
        self.model.train()
        train_loss = 0
        for batch, data in enumerate(self.data_loader):
            # debug(f'epoch {epoch+1}, batch {batch+1} start.')
            data = data.to(self.device)
            s, out, out_adj, spectral_loss, ortho_loss, cluster_loss = self.model(data.x, data.adj, data.mask)
            bin_spectral_loss, bin_ortho_loss, bin_cluster_loss = binary_pooling_loss(s=s,
                                                                                      out_adj=out_adj,
                                                                                      adj=data.adj)
            graph_pooling_loss = self.spectral_loss_weight * spectral_loss + self.ortho_loss_weight * ortho_loss + self.cluster_loss_weight * cluster_loss
            binary_graph_pooling_loss = self.bin_spectral_loss_weight * bin_spectral_loss + self.bin_ortho_loss_weight * bin_ortho_loss + self.bin_cluster_loss_weight * bin_cluster_loss
            loss = graph_pooling_loss + binary_graph_pooling_loss
            feat_similarity_loss = within_cluster_variance_loss(x=data.x, s=s, mask=data.mask)
            loss = loss + self.feat_similarity_loss_weight * feat_similarity_loss
            loss.backward()
            self.optimizer.step()
            self.optimizer.zero_grad()
            # debug(f'epoch {epoch+1}, batch {batch+1} end.')
            if self.inspect_funcs is not None:
                for inspect_func in self.inspect_funcs:
                    inspect_func(epoch=epoch + 1,
                                 batch=batch + 1,
                                 data=data,
                                 s=s,
                                 out=out,
                                 out_adj=out_adj,
                                 loss=loss,
                                 spectral_loss=spectral_loss,
                                 ortho_loss=ortho_loss,
                                 cluster_loss=cluster_loss,
                                 bin_spectral_loss=bin_spectral_loss,
                                 bin_ortho_loss=bin_ortho_loss,
                                 bin_cluster_loss=bin_cluster_loss,
                                 feat_similarity_loss=feat_similarity_loss)
            train_loss += loss.item()
        return train_loss


class GSAPBatchTrain(BatchTrain):
    """
    Graph Smooth Autoencoder Pooling batch training class.
    """

    def set_train_args(self,
                       optimizer: torch.optim.Optimizer,
                       recon_loss_weight: float = 1,
                       graph_smooth_loss_weight: float = 10,
                       spectral_loss_weight: float = 1,
                       ortho_loss_weight: float = 0,
                       cluster_loss_weight: float = 1,
                       bin_spectral_loss_weight: float = 0,
                       bin_ortho_loss_weight: float = 0,
                       bin_cluster_loss_weight: float = 0,
                       feat_similarity_loss_weight: float = 0,
                       inspect_funcs: Optional[List[Callable]] = None) -> None:
        self.optimizer = optimizer
        self.recon_loss_weight = recon_loss_weight
        self.graph_smooth_loss_weight = graph_smooth_loss_weight
        self.spectral_loss_weight = spectral_loss_weight
        self.ortho_loss_weight = ortho_loss_weight
        self.cluster_loss_weight = cluster_loss_weight
        self.bin_spectral_loss_weight = bin_spectral_loss_weight
        self.bin_ortho_loss_weight = bin_ortho_loss_weight
        self.bin_cluster_loss_weight = bin_cluster_loss_weight
        self.feat_similarity_loss_weight = feat_similarity_loss_weight
        self.inspect_funcs = inspect_funcs

    def train_epoch(self, epoch: int) -> float:
        self.model.train()
        train_loss = 0
        for batch, data in enumerate(self.data_loader):
            # debug(f'epoch {epoch+1}, batch {batch+1} start.')
            data = data.to(self.device)
            recon_x, z, s, out, out_adj, spectral_loss, ortho_loss, cluster_loss = self.model(
                data.x, data.adj, data.mask)
            r_loss = recon_loss(x=data.x, recon_x=recon_x, mask=data.mask)
            g_loss = graph_smooth_loss(z=z, adj=data.adj, mask=data.mask)
            bin_spectral_loss, bin_ortho_loss, bin_cluster_loss = binary_pooling_loss(s=s,
                                                                                      out_adj=out_adj,
                                                                                      adj=data.adj)
            GSAE_loss = self.recon_loss_weight * r_loss + self.graph_smooth_loss_weight * g_loss
            graph_pooling_loss = self.spectral_loss_weight * spectral_loss + self.ortho_loss_weight * ortho_loss + self.cluster_loss_weight * cluster_loss
            binary_graph_pooling_loss = self.bin_spectral_loss_weight * bin_spectral_loss + self.bin_ortho_loss_weight * bin_ortho_loss + self.bin_cluster_loss_weight * bin_cluster_loss
            loss = GSAE_loss + graph_pooling_loss + binary_graph_pooling_loss
            feat_similarity_loss = within_cluster_variance_loss(x=data.x, s=s, mask=data.mask)
            loss = loss + self.feat_similarity_loss_weight * feat_similarity_loss
            loss.backward()
            self.optimizer.step()
            self.optimizer.zero_grad()
            # debug(f'epoch {epoch+1}, batch {batch+1} end.')
            if self.inspect_funcs is not None:
                for inspect_func in self.inspect_funcs:
                    inspect_func(epoch=epoch + 1,
                                 batch=batch + 1,
                                 data=data,
                                 recon_x=recon_x,
                                 z=z,
                                 s=s,
                                 out=out,
                                 out_adj=out_adj,
                                 loss=loss,
                                 recon_loss=r_loss,
                                 graph_smooth_loss=g_loss,
                                 spectral_loss=spectral_loss,
                                 ortho_loss=ortho_loss,
                                 cluster_loss=cluster_loss,
                                 bin_spectral_loss=bin_spectral_loss,
                                 bin_ortho_loss=bin_ortho_loss,
                                 bin_cluster_loss=bin_cluster_loss,
                                 feat_similarity_loss=feat_similarity_loss)
            train_loss += loss.item()
        return train_loss

    def evaluate(self) -> Dict[str, np.floating]:
        """
        Evaluate the model.
        :return: results_dict
        """
        self.model.eval()
        r_loss_list, g_loss_list, spectral_loss_list, ortho_loss_list, cluster_loss_list = [], [], [], [], []
        bin_spectral_loss_list, bin_ortho_loss_list, bin_cluster_loss_list = [], [], []
        feat_similarity_loss_list = []
        loss_list = []
        with torch.no_grad():
            for data in self.data_loader:
                data = data.to(self.device)
                recon_x, z, s, out, out_adj, spectral_loss, ortho_loss, cluster_loss = self.model.evaluate(
                    data.x, data.adj, data.mask)
                r_loss = recon_loss(x=data.x, recon_x=recon_x, mask=data.mask)
                g_loss = graph_smooth_loss(z=z, adj=data.adj, mask=data.mask)
                GSAE_loss = self.recon_loss_weight * r_loss + self.graph_smooth_loss_weight * g_loss
                graph_pooling_loss = self.spectral_loss_weight * spectral_loss + self.ortho_loss_weight * ortho_loss + self.cluster_loss_weight * cluster_loss
                bin_spectral_loss, bin_ortho_loss, bin_cluster_loss = binary_pooling_loss(s=s,
                                                                                          out_adj=out_adj,
                                                                                          adj=data.adj)
                binary_graph_pooling_loss = self.bin_spectral_loss_weight * bin_spectral_loss + self.bin_ortho_loss_weight * bin_ortho_loss + self.bin_cluster_loss_weight * bin_cluster_loss
                loss = GSAE_loss + graph_pooling_loss + binary_graph_pooling_loss
                feat_similarity_loss = within_cluster_variance_loss(x=data.x, s=s, mask=data.mask)
                loss = loss + self.feat_similarity_loss_weight * feat_similarity_loss
                r_loss_list.append(r_loss.item())
                g_loss_list.append(g_loss.item())
                spectral_loss_list.append(spectral_loss.item())
                ortho_loss_list.append(ortho_loss.item())
                cluster_loss_list.append(cluster_loss.item())
                bin_spectral_loss_list.append(bin_spectral_loss.item())
                bin_ortho_loss_list.append(bin_ortho_loss.item())
                bin_cluster_loss_list.append(bin_cluster_loss.item())
                feat_similarity_loss_list.append(feat_similarity_loss.item())
                loss_list.append(loss.item())
        r_loss = np.mean(r_loss_list)
        g_loss = np.mean(g_loss_list)
        spectral_loss = np.mean(spectral_loss_list)
        ortho_loss = np.mean(ortho_loss_list)
        cluster_loss = np.mean(cluster_loss_list)
        bin_spectral_loss = np.mean(bin_spectral_loss_list)
        bin_ortho_loss = np.mean(bin_ortho_loss_list)
        bin_cluster_loss = np.mean(bin_cluster_loss_list)
        feat_similarity_loss = np.mean(feat_similarity_loss_list)
        loss = np.mean(loss_list)
        results_dict = {
            'recon_loss': r_loss,
            'graph_smooth_loss': g_loss,
            'spectral_loss': spectral_loss,
            'ortho_loss': ortho_loss,
            'cluster_loss': cluster_loss,
            'bin_spectral_loss': bin_spectral_loss,
            'bin_ortho_loss': bin_ortho_loss,
            'bin_cluster_loss': bin_cluster_loss,
            'feat_similarity_loss': feat_similarity_loss,
            'total_loss': loss
        }
        return results_dict

    def predict_dict(self, data: Data) -> Dict[str, Tensor]:
        self.model.eval()
        with torch.no_grad():
            z, s, out, out_adj = self.model.predict(data.x, data.adj, data.mask)
            recon_x = self.model.predict_recon(data.x, data.adj, data.mask)
        return {'z': z, 's': s, 'out': out, 'out_adj': out_adj, 'recon_x': recon_x}

    def predict_recon(self, data: Data) -> Tensor:
        self.model.eval()
        with torch.no_grad():
            recon_x = self.model.predict_recon(data.x, data.adj, data.mask)  # type: ignore
        return recon_x


class GPBatchTrain(BatchTrain):
    """
    Graph Pooling batch training class.
    """

    @selective_args_decorator
    def set_train_args(self,
                       optimizer: torch.optim.Optimizer,
                       spectral_loss_weight: float = 1,
                       ortho_loss_weight: float = 0,
                       cluster_loss_weight: float = 1,
                       bin_spectrum_loss_weight: float = 0,
                       bin_ortho_loss_weight: float = 0,
                       bin_cluster_loss_weight: float = 0,
                       feat_similarity_loss_weight: float = 0,
                       inspect_funcs: Optional[List[Callable]] = None) -> None:
        self.optimizer = optimizer
        self.spectral_loss_weight = spectral_loss_weight
        self.ortho_loss_weight = ortho_loss_weight
        self.cluster_loss_weight = cluster_loss_weight
        self.bin_spectrum_loss_weight = bin_spectrum_loss_weight
        self.bin_ortho_loss_weight = bin_ortho_loss_weight
        self.bin_cluster_loss_weight = bin_cluster_loss_weight
        self.feat_similarity_loss_weight = feat_similarity_loss_weight
        self.inspect_funcs = inspect_funcs

    def cal_loss(self, spectral_loss, ortho_loss, cluster_loss, data, s) -> Tuple[Tensor, ...]:
        spectral_loss = self.spectral_loss_weight * spectral_loss
        ortho_loss = self.ortho_loss_weight * ortho_loss * np.sqrt(2)
        cluster_loss = self.cluster_loss_weight * cluster_loss / (np.sqrt(self.model.k) - 1)
        feat_similarity_loss = within_cluster_variance_loss(x=data.x, s=s, mask=data.mask)
        total_var = masked_variance(x=data.x, mask=data.mask)
        feat_similarity_loss = self.feat_similarity_loss_weight * feat_similarity_loss
        loss = spectral_loss + ortho_loss + cluster_loss + feat_similarity_loss

        return loss, spectral_loss, ortho_loss, cluster_loss, feat_similarity_loss

    def train_epoch(self, epoch: int) -> float:
        self.model.train()
        train_loss = 0
        for batch, data in enumerate(self.data_loader):
            # debug(f'epoch {epoch+1}, batch {batch+1} start.')
            data = data.to(self.device)
            s, out, out_adj, spectral_loss, ortho_loss, cluster_loss = self.model(data.x, data.adj, data.mask)
            loss, spectral_loss, ortho_loss, cluster_loss, feat_similarity_loss = self.cal_loss(
                spectral_loss, ortho_loss, cluster_loss, data, s)
            loss.backward()
            self.optimizer.step()
            self.optimizer.zero_grad()
            # debug(f'epoch {epoch+1}, batch {batch+1} end.')
            if self.inspect_funcs is not None:
                for inspect_func in self.inspect_funcs:
                    inspect_func(
                        epoch=epoch + 1,
                        batch=batch + 1,
                        data=data,
                        s=s,
                        out=out,
                        out_adj=out_adj,
                        loss=loss,
                        spectral_loss=spectral_loss,
                        # ortho_loss=ortho_loss,
                        cluster_loss=cluster_loss,
                        #  bin_spectral_loss=bin_spectral_loss,
                        #  bin_ortho_loss=bin_ortho_loss,
                        #  bin_cluster_loss=bin_cluster_loss,
                        feat_similarity_loss=feat_similarity_loss)
            train_loss += loss.item()
        return train_loss

    def evaluate(self) -> Dict[str, np.floating]:
        """
        Evaluate the model.
        :return: results_dict
        """
        spectral_loss_list, ortho_loss_list, cluster_loss_list = [], [], []
        # bin_spectral_loss_list, bin_ortho_loss_list, bin_cluster_loss_list = [], [], []
        feat_similarity_loss_list = []
        loss_list = []
        self.model.eval()
        with torch.no_grad():
            for data in self.data_loader:
                data = data.to(self.device)
                s, out, out_adj, spectral_loss, ortho_loss, cluster_loss = self.model.evaluate(
                    data.x, data.adj, data.mask)
                loss, spectral_loss, ortho_loss, cluster_loss, feat_similarity_loss = self.cal_loss(
                    spectral_loss, ortho_loss, cluster_loss, data, s)

                spectral_loss_list.append(spectral_loss.item())
                # ortho_loss_list.append(ortho_loss.item())
                cluster_loss_list.append(cluster_loss.item())
                # bin_spectral_loss_list.append(bin_spectral_loss.item())
                # bin_ortho_loss_list.append(bin_ortho_loss.item())
                # bin_cluster_loss_list.append(bin_cluster_loss.item())
                feat_similarity_loss_list.append(feat_similarity_loss.item())
                loss_list.append(loss.item())
        spectral_loss = np.mean(spectral_loss_list)
        # ortho_loss = np.mean(ortho_loss_list)
        cluster_loss = np.mean(cluster_loss_list)
        # bin_spectral_loss = np.mean(bin_spectral_loss_list)
        # bin_ortho_loss = np.mean(bin_ortho_loss_list)
        # bin_cluster_loss = np.mean(bin_cluster_loss_list)
        feat_similarity_loss = np.mean(feat_similarity_loss_list)
        loss = np.mean(loss_list)
        results_dict = {
            'spectral_loss': spectral_loss,
            # 'ortho_loss': ortho_loss,
            'cluster_loss': cluster_loss,
            # 'bin_spectral_loss': bin_spectral_loss,
            # 'bin_ortho_loss': bin_ortho_loss,
            # 'bin_cluster_loss': bin_cluster_loss,
            'feat_similarity_loss': feat_similarity_loss,
            'total_loss': loss
        }
        return results_dict

    def predict_dict(self, data: Data) -> Dict[str, Tensor]:
        self.model.eval()
        with torch.no_grad():
            s, out, out_adj = self.model.predict(data.x, data.adj, data.mask)
            z = self.model.predict_embed(data.x, data.adj, data.mask)
        return {'z': z, 's': s, 'out': out, 'out_adj': out_adj}

    def predict_embed(self, data: Data) -> Tensor:
        self.model.eval()
        with torch.no_grad():
            z = self.model.predict_embed(data.x, data.adj, data.mask)  # type: ignore
        return z


__all__ = ['SubBatchTrainProtocol', 'GSAEBatchTrain', 'NPBatchTrain', 'GSAPBatchTrain', 'GPBatchTrain']
