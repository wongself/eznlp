# -*- coding: utf-8 -*-
import pytest
import torch
from torch.nn.utils.rnn import pad_sequence
import flair

from eznlp.data import Batch
from eznlp import PreTrainedEmbedderConfig
from eznlp.training import count_params



class TestFlairEmbedder(object):
    @pytest.mark.parametrize("flair_forward", [True, False])
    @pytest.mark.parametrize("agg_mode", ['last', 'mean'])
    def test_flair_embeddings(self, flair_fw_lm, flair_bw_lm, flair_forward, agg_mode):
        batch_tokenized_text = [["I", "like", "it", "."], 
                                ["Do", "you", "love", "me", "?"], 
                                ["Sure", "!"], 
                                ["Future", "it", "out"]]
        
        flair_lm = flair_fw_lm if flair_forward else flair_bw_lm
        flair_emb = flair.embeddings.FlairEmbeddings(flair_lm)
        flair_sentences = [flair.data.Sentence(" ".join(sent), use_tokenizer=False) for sent in batch_tokenized_text]
        flair_emb.embed(flair_sentences)
        expected = pad_sequence([torch.stack([tok.embedding for tok in sent]) for sent in flair_sentences], 
                                batch_first=True, padding_value=0.0)
        
        flair_embedder_config = PreTrainedEmbedderConfig(arch='Flair', out_dim=flair_lm.hidden_size, agg_mode=agg_mode)
        flair_embedder = flair_embedder_config.instantiate(flair_lm)
        batch = Batch(tokenized_raw_text=batch_tokenized_text, tok_ids=torch.randint(0, 5, size=(4, 5)))
        
        if agg_mode.lower() == 'last':
            assert (flair_embedder(batch) == expected).all().item()
        else:
            assert (flair_embedder(batch) != expected).any().item()
            
            
    @pytest.mark.parametrize("flair_forward", [True, False])
    @pytest.mark.parametrize("freeze", [True, False])
    @pytest.mark.parametrize("use_gamma", [True, False])
    def test_trainble_config(self, flair_fw_lm, flair_bw_lm, flair_forward, freeze, use_gamma):
        flair_lm = flair_fw_lm if flair_forward else flair_bw_lm
        flair_embedder_config = PreTrainedEmbedderConfig(arch='Flair', out_dim=flair_lm.hidden_size, 
                                                         freeze=freeze, use_gamma=use_gamma)
        flair_embedder = flair_embedder_config.instantiate(flair_lm)
        
        expected_num_trainable_params = 0
        if not freeze:
            expected_num_trainable_params += count_params(flair_lm, return_trainable=False)
        if use_gamma:
            expected_num_trainable_params += 1
        assert count_params(flair_embedder, verbose=False) == expected_num_trainable_params
        
        
class TestELMoEmbbeder(object):
    @pytest.mark.parametrize("mix_layers", ['trainable', 'top', 'average'])
    @pytest.mark.parametrize("freeze", [True, False])
    @pytest.mark.parametrize("use_gamma", [True, False])
    def test_trainble_config(self, elmo, freeze, mix_layers, use_gamma):
        elmo_embedder_config = PreTrainedEmbedderConfig(arch='ELMo', out_dim=elmo.get_output_dim(), 
                                                        freeze=freeze, mix_layers=mix_layers, use_gamma=use_gamma)
        elmo_embedder = elmo_embedder_config.instantiate(elmo)
        
        expected_num_trainable_params = 0
        if not freeze:
            expected_num_trainable_params += count_params(elmo, return_trainable=False) - 4
        if mix_layers.lower() == 'trainable':
            expected_num_trainable_params += 3
        if use_gamma:
            expected_num_trainable_params += 1
        
        assert count_params(elmo_embedder, verbose=False) == expected_num_trainable_params
        
        
class TestBertEmbedder(object):
    @pytest.mark.parametrize("mix_layers", ['trainable', 'top'])
    @pytest.mark.parametrize("freeze", [True])
    @pytest.mark.parametrize("use_gamma", [True])
    def test_trainble_config(self, bert_with_tokenizer, freeze, mix_layers, use_gamma):
        bert, tokenizer = bert_with_tokenizer
        bert_embedder_config = PreTrainedEmbedderConfig(arch='BERT', out_dim=bert.config.hidden_size, tokenizer=tokenizer,
                                                        freeze=freeze, mix_layers=mix_layers, use_gamma=use_gamma)
        bert_embedder = bert_embedder_config.instantiate(bert)
        
        expected_num_trainable_params = 0
        if not freeze:
            expected_num_trainable_params += count_params(bert, return_trainable=False)
        if mix_layers.lower() == 'trainable':
            expected_num_trainable_params += 13
        if use_gamma:
            expected_num_trainable_params += 1
        
        assert count_params(bert_embedder, verbose=False) == expected_num_trainable_params
        
        