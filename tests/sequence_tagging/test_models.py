# -*- coding: utf-8 -*-
import pytest
import torch

from eznlp.token import Token
from eznlp.config import ConfigDict
from eznlp.model import OneHotConfig, MultiHotConfig, EncoderConfig
from eznlp.pretrained import ELMoConfig, BertLikeConfig, FlairConfig
from eznlp.sequence_tagging import SequenceTaggingDecoderConfig, SequenceTaggerConfig
from eznlp.sequence_tagging import SequenceTaggingDataset
from eznlp.sequence_tagging import SequenceTaggingTrainer



class TestTagger(object):
    def one_tagger_pass(self, tagger, dataset, device):
        tagger.eval()
        
        batch012 = dataset.collate([dataset[i] for i in range(0, 3)]).to(device)
        batch123 = dataset.collate([dataset[i] for i in range(1, 4)]).to(device)
        losses012, hidden012 = tagger(batch012, return_hidden=True)
        losses123, hidden123 = tagger(batch123, return_hidden=True)
        
        min_step = min(hidden012.size(1), hidden123.size(1))
        delta_hidden = hidden012[1:, :min_step] - hidden123[:-1, :min_step]
        assert delta_hidden.abs().max().item() < 1e-4
        
        delta_losses = losses012[1:] - losses123[:-1]
        assert delta_losses.abs().max().item() < 2e-4
        
        best_paths012 = tagger.decode(batch012)
        best_paths123 = tagger.decode(batch123)
        assert best_paths012[1:] == best_paths123[:-1]
        
        optimizer = torch.optim.AdamW(tagger.parameters())
        trainer = SequenceTaggingTrainer(tagger, optimizer=optimizer, device=device)
        trainer.train_epoch([batch012])
        trainer.eval_epoch([batch012])
        
        
    @pytest.mark.parametrize("enc_arch", ['CNN', 'LSTM', 'GRU', 'Transformer'])
    @pytest.mark.parametrize("shortcut", [False, True])
    @pytest.mark.parametrize("dec_arch", ['softmax', 'CRF'])
    def test_tagger(self, conll2003_demo, enc_arch, shortcut, dec_arch, device):
        config = SequenceTaggerConfig(encoder=EncoderConfig(arch=enc_arch, shortcut=shortcut), 
                                      decoder=SequenceTaggingDecoderConfig(arch=dec_arch))
        
        dataset = SequenceTaggingDataset(conll2003_demo, config)
        dataset.build_vocabs_and_dims()
        tagger = config.instantiate().to(device)
        self.one_tagger_pass(tagger, dataset, device)
        
        
    @pytest.mark.parametrize("freeze", [False, True])
    def test_word_embedding_initialization(self, conll2003_demo, glove100, freeze, device):
        config = SequenceTaggerConfig(ohots=ConfigDict({'text': OneHotConfig(field='text', vectors=glove100, freeze=freeze)}))
        
        dataset = SequenceTaggingDataset(conll2003_demo, config)
        dataset.build_vocabs_and_dims()
        tagger = config.instantiate().to(device)
        self.one_tagger_pass(tagger, dataset, device)
        
        
    def test_tagger_intermediate(self, conll2003_demo, device):
        config = SequenceTaggerConfig(intermediate=EncoderConfig())
        
        dataset = SequenceTaggingDataset(conll2003_demo, config)
        dataset.build_vocabs_and_dims()
        tagger = config.instantiate().to(device)
        self.one_tagger_pass(tagger, dataset, device)
        
        
    @pytest.mark.parametrize("freeze", [False, True])
    def test_tagger_elmo(self, conll2003_demo, elmo, freeze, device):
        config = SequenceTaggerConfig(ohots=None, 
                                      encoder=None, 
                                      elmo=ELMoConfig(elmo=elmo))
        
        dataset = SequenceTaggingDataset(conll2003_demo, config)
        dataset.build_vocabs_and_dims()
        tagger = config.instantiate().to(device)
        self.one_tagger_pass(tagger, dataset, device)
        
        
    @pytest.mark.parametrize("freeze", [False, True])
    def test_tagger_bert_like(self, conll2003_demo, bert_with_tokenizer, freeze, device):
        bert, tokenizer = bert_with_tokenizer
        config = SequenceTaggerConfig(ohots=None, 
                                      encoder=None, 
                                      bert_like=BertLikeConfig(bert_like=bert, tokenizer=tokenizer, freeze=freeze))
        
        dataset = SequenceTaggingDataset(conll2003_demo, config)
        dataset.build_vocabs_and_dims()
        tagger = config.instantiate().to(device)
        self.one_tagger_pass(tagger, dataset, device)
        
        
    @pytest.mark.parametrize("freeze", [False, True])
    def test_tagger_flair(self, conll2003_demo, flair_fw_lm, flair_bw_lm, freeze, device):
        config = SequenceTaggerConfig(ohots=None, 
                                      encoder=None, 
                                      flair_fw=FlairConfig(flair_lm=flair_fw_lm, freeze=freeze),  
                                      flair_bw=FlairConfig(flair_lm=flair_bw_lm, freeze=freeze))
        
        dataset = SequenceTaggingDataset(conll2003_demo, config)
        dataset.build_vocabs_and_dims()
        tagger = config.instantiate().to(device)
        self.one_tagger_pass(tagger, dataset, device)
        
        
    @pytest.mark.parametrize("enc_arch", ['CNN', 'LSTM'])
    def test_tagger_morefields(self, conll2003_demo, enc_arch, device):
        config = SequenceTaggerConfig(ohots=ConfigDict({f: OneHotConfig(field=f, emb_dim=20) for f in Token._basic_ohot_fields}), 
                                      mhots=ConfigDict({f: MultiHotConfig(field=f, emb_dim=20) for f in Token._basic_mhot_fields}), 
                                      encoder=EncoderConfig(arch=enc_arch))
        
        dataset = SequenceTaggingDataset(conll2003_demo, config)
        dataset.build_vocabs_and_dims()
        tagger = config.instantiate().to(device)
        self.one_tagger_pass(tagger, dataset, device)
        
        
    @pytest.mark.parametrize("scheme", ['BIO1', 'BIO2'])
    def test_tagger_schemes(self, conll2003_demo, scheme, device):
        config = SequenceTaggerConfig(decoder=SequenceTaggingDecoderConfig(scheme=scheme))
        
        dataset = SequenceTaggingDataset(conll2003_demo, config)
        dataset.build_vocabs_and_dims()
        tagger = config.instantiate().to(device)
        self.one_tagger_pass(tagger, dataset, device)
        
        
    @pytest.mark.parametrize("use_amp", [False, True])
    def test_train_steps(self, conll2003_demo, use_amp, device):
        dataset = SequenceTaggingDataset(conll2003_demo)
        dataset.build_vocabs_and_dims()
        tagger = dataset.config.instantiate().to(device)
        
        dataloader = torch.utils.data.DataLoader(dataset, batch_size=4, shuffle=True, collate_fn=dataset.collate)
        optimizer = torch.optim.AdamW(tagger.parameters())
        trainer = SequenceTaggingTrainer(tagger, optimizer=optimizer, use_amp=use_amp, device=device)
        trainer.train_steps(train_loader=dataloader, 
                            dev_loader=dataloader, 
                            num_epochs=8, disp_every_steps=2, eval_every_steps=4)
        