# -*- coding: utf-8 -*-
import pytest
import torch

from eznlp.dataset import Dataset
from eznlp.model import EncoderConfig, BertLikeConfig, ModelConfig
from eznlp.model import SequenceTaggingDecoderConfig, BoundarySelectionDecoderConfig
from eznlp.model import SpanClassificationDecoderConfig, SpanAttrClassificationDecoderConfig, SpanRelClassificationDecoderConfig
from eznlp.model import JointExtractionDecoderConfig
from eznlp.training import Trainer


class TestModel(object):
    def _assert_batch_consistency(self):
        self.model.eval()
        
        batch = [self.dataset[i] for i in range(4)]
        batch012 = self.dataset.collate(batch[:3]).to(self.device)
        batch123 = self.dataset.collate(batch[1:]).to(self.device)
        losses012, hidden012 = self.model(batch012, return_hidden=True)
        losses123, hidden123 = self.model(batch123, return_hidden=True)
        
        min_step = min(hidden012.size(1), hidden123.size(1))
        delta_hidden = hidden012[1:, :min_step] - hidden123[:-1, :min_step]
        assert delta_hidden.abs().max().item() < 2e-4
        
        delta_losses = losses012[1:] - losses123[:-1]
        assert delta_losses.abs().max().item() < 1e-3
        
        y_pred012 = self.model.decode(batch012)
        y_pred123 = self.model.decode(batch123)
        assert all(tuples_pred012[1:] == tuples_pred123[:-1] for tuples_pred012, tuples_pred123 in zip(y_pred012, y_pred123))
        
        
    def _assert_trainable(self):
        optimizer = torch.optim.AdamW(self.model.parameters())
        trainer = Trainer(self.model, optimizer=optimizer, device=self.device)
        dataloader = torch.utils.data.DataLoader(self.dataset, 
                                                 batch_size=4, 
                                                 shuffle=True, 
                                                 collate_fn=self.dataset.collate)
        trainer.train_epoch(dataloader)
        
        
    def _setup_case(self, data, device):
        self.device = device
        
        self.dataset = Dataset(data, self.config)
        self.dataset.build_vocabs_and_dims()
        self.model = self.config.instantiate().to(self.device)
        assert isinstance(self.config.name, str) and len(self.config.name) > 0
        
        
    @pytest.mark.parametrize("ck_decoder", ['sequence_tagging', 'span_classification', 'boundary_selection'])
    @pytest.mark.parametrize("agg_mode", ['max_pooling'])
    @pytest.mark.parametrize("fl_gamma", [0.0, 2.0])
    def test_model(self, ck_decoder, agg_mode, fl_gamma, HwaMei_demo, device):
        if ck_decoder.lower() == 'sequence_tagging':
            ck_decoder_config = SequenceTaggingDecoderConfig(use_crf=True)
        elif ck_decoder.lower() == 'span_classification':
            ck_decoder_config = SpanClassificationDecoderConfig(agg_mode=agg_mode, fl_gamma=fl_gamma)
        elif ck_decoder.lower() == 'boundary_selection':
            ck_decoder_config = BoundarySelectionDecoderConfig(fl_gamma=fl_gamma)
        self.config = ModelConfig(decoder=JointExtractionDecoderConfig(ck_decoder=ck_decoder_config, 
                                                                       attr_decoder=SpanAttrClassificationDecoderConfig(agg_mode=agg_mode), 
                                                                       rel_decoder=SpanRelClassificationDecoderConfig(agg_mode=agg_mode, fl_gamma=fl_gamma)))
        self._setup_case(HwaMei_demo, device)
        self._assert_batch_consistency()
        self._assert_trainable()
        
        
    def test_model_with_bert_like(self, HwaMei_demo, bert_with_tokenizer, device):
        bert, tokenizer = bert_with_tokenizer
        self.config = ModelConfig('joint_extraction', 
                                  ohots=None, 
                                  bert_like=BertLikeConfig(tokenizer=tokenizer, bert_like=bert), 
                                  intermediate2=None)
        self._setup_case(HwaMei_demo, device)
        self._assert_batch_consistency()
        self._assert_trainable()
        
        
    def test_prediction_without_gold(self, HwaMei_demo, device):
        self.config = ModelConfig('joint_extraction')
        self._setup_case(HwaMei_demo, device)
        
        data_wo_gold = [{'tokens': entry['tokens']} for entry in HwaMei_demo]
        dataset_wo_gold = Dataset(data_wo_gold, self.config, training=False)
        
        trainer = Trainer(self.model, device=device)
        assert all(len(set_tuples_pred) == len(data_wo_gold) for set_tuples_pred in trainer.predict(dataset_wo_gold))
