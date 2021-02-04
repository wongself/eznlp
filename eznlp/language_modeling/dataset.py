# -*- coding: utf-8 -*-
import random
import logging
import torch

from ..data.wrapper import TensorWrapper, Batch
from ..data.dataset import Dataset
from ..nn.functional import seq_lens2mask

logger = logging.getLogger(__name__)


class MLMHelper(object):
    def __init__(self, tokenizer, MLM_prob=0.15):
        self.cls_id = tokenizer.cls_token_id
        self.sep_id = tokenizer.sep_token_id
        self.unk_id = tokenizer.unk_token_id
        self.pad_id = tokenizer.pad_token_id
        self.mask_id = tokenizer.mask_token_id
        
        self.stoi = tokenizer.get_vocab()
        self.special_ids = list(set(tokenizer.all_special_ids))
        self.non_special_ids = [idx for idx in range(len(self.stoi)) if idx not in self.special_ids]
        
        # Tokens with indices set to ``-100`` are ignored (masked), the loss is only 
        # computed for the tokens with labels in ``[0, ..., config.vocab_size]
        self.MLM_label_mask_id = -100
        self.MLM_prob = MLM_prob
        
        
    def build_example(self, token_list):
        MLM_tok_ids = [self.cls_id] + [self.stoi[tok] for tok in token_list] + [self.sep_id]
        MLM_lab_ids = []
        for k, tok_id in enumerate(MLM_tok_ids):
            if (tok_id not in self.special_ids) and (random.random() < self.MLM_prob):
                random_v = random.random()
                if random_v < 0.8:
                    # Replace with `[MASK]`
                    MLM_tok_ids[k] = self.mask_id
                elif random_v < 0.9:
                    # Replace with a random token
                    MLM_tok_ids[k] = random.choice(self.non_special_ids)
                else:
                    # Retain the original token
                    pass
                MLM_lab_ids.append(tok_id)
            else:
                MLM_lab_ids.append(self.MLM_label_mask_id)
                
        return TensorWrapper(MLM_tok_ids=torch.tensor(MLM_tok_ids), 
                             MLM_lab_ids=torch.tensor(MLM_lab_ids))

    
    def collate(self, batch_examples):
        batch_MLM_tok_ids = []
        batch_MLM_lab_ids = []
        
        for ex in batch_examples:
            batch_MLM_tok_ids.append(ex.MLM_tok_ids)
            batch_MLM_lab_ids.append(ex.MLM_lab_ids)
        
        seq_lens = torch.tensor([s.size(0) for s in batch_MLM_tok_ids])
        batch_MLM_tok_ids = torch.nn.utils.rnn.pad_sequence(batch_MLM_tok_ids, batch_first=True, padding_value=self.pad_id)
        batch_MLM_lab_ids = torch.nn.utils.rnn.pad_sequence(batch_MLM_lab_ids, batch_first=True, padding_value=self.MLM_label_mask_id)
        attention_mask = seq_lens2mask(seq_lens, batch_MLM_tok_ids.size(1))
        
        return Batch(seq_lens=seq_lens, 
                     MLM_tok_ids=batch_MLM_tok_ids, 
                     MLM_lab_ids=batch_MLM_lab_ids, 
                     attention_mask=attention_mask)


class MLMDataset(Dataset):
    """
    Dataset for Masked Language Modeling. 
    """
    def __init__(self, data, tokenizer, MLM_prob=0.15):
        super().__init__(data, None)
        self.tokenizer = tokenizer
        self.mlm_helper = MLMHelper(tokenizer, MLM_prob=MLM_prob)
        
    def __getitem__(self, i):
        """
        Dynamic Masking.
        """
        curr_data = self.data[i]
        tokenized_raw_text = curr_data['tokens'].raw_text
        
        nested_sub_tokens = [self.tokenizer.tokenize(word) for word in tokenized_raw_text]
        sub_tokens = [sub_tok for i, tok in enumerate(nested_sub_tokens) for sub_tok in tok]
        return self.mlm_helper.build_example(sub_tokens)
    
    def collate(self, batch_examples):
        return self.mlm_helper.collate(batch_examples)
        
    
    
def _slice_chunk(chunk_id, num_chunks, num_items):
    assert chunk_id >= 0 and num_chunks > 0 and chunk_id < num_chunks
    
    chunk_size = num_items / num_chunks
    start = int(chunk_size* chunk_id    + 0.5)
    end   = int(chunk_size*(chunk_id+1) + 0.5)
    return slice(start, end)


class PMCMLMDataset(torch.utils.data.IterableDataset):
    """
    PMC Dataset for Masked Language Modeling. 
    """
    def __init__(self, files, tokenizer, MLM_prob=0.15, max_len=512, shuffle=True, 
                 mp_rank=0, mp_world_size=0, verbose=True):
        super().__init__()
        if mp_rank >= 0 and mp_world_size > 0 and mp_rank < mp_world_size:
            files = files[_slice_chunk(mp_rank, mp_world_size, len(files))]
        if verbose:
            logger.info(f"Totally {len(files)} files in the {mp_rank}-th process")
            
        self.files = files
        self.tokenizer = tokenizer
        self.mlm_helper = MLMHelper(tokenizer, MLM_prob=MLM_prob)
        self.max_len = max_len
        self.shuffle = shuffle
        
    def __iter__(self):
        cut_len = self.max_len - 2
        
        worker_info = torch.utils.data.get_worker_info()
        if worker_info is None:
            # single-process data loading, return the full iterator
            this_files = self.files[:]
        else:
            # in a worker process -> split workload
            this_files = self.files[_slice_chunk(worker_info.id, worker_info.num_workers, len(self.files))]
            
        if self.shuffle:
            random.shuffle(this_files)
            
        for file_name in this_files:
            try:
                with open(file_name, encoding='utf-8') as f:
                    text = f.read()
            except:
                continue
            
            token_list = self.tokenizer.tokenize(text)
            n_examples = len(token_list) // cut_len
            if len(token_list) % cut_len >= (cut_len / 10):
                n_examples += 1
            
            for k in range(n_examples):
                this_token_list = token_list[(cut_len*k):(cut_len*(k+1))]
                yield self.mlm_helper.build_example(this_token_list)
                
                
    def collate(self, batch_examples):
        return self.mlm_helper.collate(batch_examples)
    

