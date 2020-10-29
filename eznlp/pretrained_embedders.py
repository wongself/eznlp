# -*- coding: utf-8 -*-
import torch
import torch.nn as nn
from transformers import PreTrainedModel
from allennlp.modules.elmo import Elmo

from .datasets_utils import Batch
from .functional import aggregate_tensor_by_group
from .config import Config


class PreTrainedEmbedderConfig(Config):
    def __init__(self, **kwargs):
        self.arch = kwargs.pop('arch')
        self.out_dim = kwargs.pop('out_dim')
        self.freeze = kwargs.pop('freeze', False)
        
        if self.arch.lower() == 'elmo':
            self.lstm_stateful = kwargs.pop('lstm_stateful', False)
        elif self.arch.lower() in ('bert', 'roberta', 'albert'):
            self.tokenizer = kwargs.pop('tokenizer')
        else:
            raise ValueError(f"Invalid pretrained embedder architecture {self.arch}")
        
        super().__init__(**kwargs)
        
        
    def instantiate(self, pretrained_model: nn.Module):
        if self.arch.lower() == 'elmo':
            return ELMoEmbedder(self, pretrained_model)
        elif self.arch.lower() in ('bert', 'roberta', 'albert'):
            return BertLikeEmbedder(self, pretrained_model)
        
        
class PreTrainedEmbedder(nn.Module):
    """
    `PreTrainedEmbedder` forwards from inputs to hidden states. 
    """
    def __init__(self, config: PreTrainedEmbedderConfig, pretrained_model: nn.Module):
        super().__init__()
        self.pretrained_model = pretrained_model
        self.freeze = config.freeze
        
    @property
    def freeze(self):
        return self._freeze
    
    @freeze.setter
    def freeze(self, value: bool):
        assert isinstance(value, bool)
        self._freeze = value
        self.pretrained_model.requires_grad_(not self._freeze)
        
    def _forward(self, batch: Batch):
        raise NotImplementedError("Not Implemented `_forward`")
    
    def forward(self, batch: Batch):
        if self.freeze:
            with torch.no_grad():
                ptm_outs = self._forward(batch)
        else:
            ptm_outs = self._forward(batch)
        return ptm_outs
    
    
class BertLikeEmbedder(PreTrainedEmbedder):
    def __init__(self, config: PreTrainedEmbedderConfig, bert_like: PreTrainedModel):
        super().__init__(config, bert_like)
        
    def _forward(self, batch: Batch):
        # ptm_outs: (batch, sub_tok_step+2, hid_dim)
        ptm_outs, *_ = self.pretrained_model(input_ids=batch.sub_tok_ids, 
                                             attention_mask=(~batch.sub_tok_mask).type(torch.long))
        # Remove the `[CLS]` and `[SEP]` positions. 
        ptm_outs = ptm_outs[:, 1:-1]
        
        # agg_ptm_outs: (batch, tok_step, hid_dim)
        agg_ptm_outs = aggregate_tensor_by_group(ptm_outs, batch.ori_indexes, agg_step=batch.tok_ids.size(1))
        return agg_ptm_outs
    
    
class ELMoEmbedder(PreTrainedEmbedder):
    """
    Setting the `stateful` attribute to False can make the ELMo outputs consistent.  
    See: https://github.com/allenai/allennlp/issues/2398
    """
    def __init__(self, config: PreTrainedEmbedderConfig, elmo: Elmo):
        # TODO: Layer weights?
        elmo._elmo_lstm._elmo_lstm.stateful = config.lstm_stateful
        super().__init__(config, elmo)
        
    def _forward(self, batch: Batch):
        # TODO: use `word_inputs`?
        elmo_outs = self.pretrained_model(inputs=batch.elmo_char_ids)
        
        return elmo_outs['elmo_representations'][0]
    
    
    