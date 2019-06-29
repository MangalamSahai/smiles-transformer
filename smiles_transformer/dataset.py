import random
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader

from enumerator import SmilesEnumerator
from utils import split

PAD = 0

class Randomizer(object):

    def __init__(self):
        self.sme = SmilesEnumerator()
    
    def __call__(self, sm):
        sm = self.sme.randomize_smiles(sm) # Random transoform
        sm = split(sm) # Spacing
        return sm.split() # List

    def random_transform(self, sm):
        '''
        function: Random transformation for SMILES. It may take some time.
        input: A SMILES
        output: A randomized SMILES
        '''
        return self.sme.randomize_smiles(sm)

class STDataset(Dataset):

    def __init__(self, corpus_path, vocab, seq_len=220, transform=Randomizer(), is_train=True):
        self.vocab = vocab
        self.seq_len = seq_len
        self.is_train = is_train
        self.transform = transform
        df = pd.read_csv(corpus_path)
        self.data_size = len(df)
        self.firsts = df['first'].values
        self.seconds = df['second'].values
        max_size = 10000
        if (not is_train) and self.data_size>max_size:
            self.firsts = self.firsts[:max_size]
            self.seconds = self.seconds[:max_size]

    def __len__(self):
        return len(self.smiles)

    def __getitem__(self, item):
        sm1, (sm2, is_same_label) = self.firsts[item], self.get_random_pair(item)
        sm1 = self.transform(sm1) # List
        sm2 = self.transform(sm2) # List
        masked_ids1, ans_ids1 = self.mask(sm1)
        masked_ids2, ans_ids2 = self.mask(sm2)

        # [CLS] tag = SOS tag, [SEP] tag = EOS tag
        masked_ids1 = [self.vocab.sos_index] + masked_ids1 + [self.vocab.eos_index]
        masked_ids2 = masked_ids2 + [self.vocab.eos_index]

        ans_ids1 = [self.vocab.pad_index] + ans_ids1 + [self.vocab.pad_index]
        ans_ids2 = ans_ids2 + [self.vocab.pad_index]

        segment_embd = ([1]*len(masked_ids1) + [2]*len(masked_ids2))[:self.seq_len]
        bert_input = (masked_ids1 + masked_ids2)[:self.seq_len]
        bert_label = (ans_ids1 + ans_ids2)[:self.seq_len]

        padding = [self.vocab.pad_index]*(self.seq_len - len(bert_input))
        bert_input.extend(padding), bert_label.extend(padding), segment_embd.extend(padding)

        output = {"bert_input": bert_input,
                  "bert_label": bert_label,
                  "segment_embd": segment_embd,
                  "is_same": is_same_label}

        return {key: torch.tensor(value) for key, value in output.items()}

    def get_random_pair(self, index):
        '''
        function: Find pair molecule. The boolean is_same_label is 1 
          for same and 0 for different molecules.
        '''
        rand = random.random()
        if rand<0.5: # Same molcule
            return self.firsts[index], 1
        else: # Different (but similar) molecule
            return self.seconds[index], 0

    def mask(self, sm):
        n_token = len(sm)
        masked_ids, ans_ids = [None]*n_token, [None]*n_token
        for i, token in enumerate(sm):
            if self.is_train: # Mask probablistically when training
                prob = random.random()
            else:  # Do not mask when predicting
                prob = 1.0

            if prob > 0.15:
                masked_ids[i] = self.vocab.stoi.get(token, self.vocab.unk_index)
                ans_ids[i] = PAD
            else: # Mask
                prob /= 0.15
                # 80% randomly change token to mask token
                if prob < 0.8:
                    masked_ids[i] = self.vocab.mask_index
                # 10% randomly change token to random token
                elif prob < 0.9:
                    masked_ids[i] = random.randrange(len(self.vocab))

                # 10% randomly change token to current token
                else:
                    masked_ids[i] = self.vocab.stoi.get(token, self.vocab.unk_index)

                ans_ids[i] = self.vocab.stoi.get(token, self.vocab.unk_index)
                
        return masked_ids, ans_ids


class Seq2seqDataset(Dataset):

    def __init__(self, corpus_path, vocab, seq_len=220, transform=Randomizer(), is_train=True):
        self.vocab = vocab
        self.seq_len = seq_len
        self.is_train = is_train
        self.transform = transform
        df = pd.read_csv(corpus_path)
        self.data_size = len(df)
        self.smiles = df['first'].values
        max_size = 10000
        if (not is_train) and self.data_size>max_size:
            self.smiles = self.smiles[:max_size]

    def __len__(self):
        return len(self.smiles)

    def __getitem__(self, item):
        sm = self.smiles[item]
        sm1 = self.transform(sm) # List
        content = [self.vocab.stoi.get(token, self.vocab.unk_index) for token in sm1]
        input1 = [self.vocab.sos_index] + content + [self.vocab.eos_index]
        padding = [self.vocab.pad_index]*(self.seq_len - len(input1))
        input1.extend(padding)
        sm2 = self.transform(sm) # List
        content = [self.vocab.stoi.get(token, self.vocab.unk_index) for token in sm2]
        input2 = [self.vocab.sos_index] + content + [self.vocab.eos_index]
        padding = [self.vocab.pad_index]*(self.seq_len - len(input2))
        input2.extend(padding)
        return torch.tensor(input1), torch.tensor(input2)

class ESOLDataset(Dataset):

    def __init__(self, corpus_path, vocab, seq_len=220, transform=Randomizer()):
        self.vocab = vocab
        self.seq_len = seq_len
        self.transform = transform
        df = pd.read_csv(corpus_path)
        self.data_size = len(df)
        self.smiles = df['SMILES'].values
        self.Y = df['solubility'].values

    def __len__(self):
        return self.data_size

    def __getitem__(self, item):
        sm, y = self.smiles[item], self.Y[item]
        sm = self.transform(sm)
        sm = self.encode(sm)
        # [CLS] tag = SOS tag, [SEP] tag = EOS tag
        masked_ids = [self.vocab.sos_index] + sm + [self.vocab.eos_index]

        segment_embd = [1]*len(masked_ids)
        bert_input = masked_ids[:self.seq_len]

        padding = [self.vocab.pad_index]*(self.seq_len - len(bert_input))
        bert_input.extend(padding), segment_embd.extend(padding)

        output = {"bert_input": bert_input,
                  "segment_embd": segment_embd,
                  "target": y}
        return {key: torch.tensor(value) for key, value in output.items()}

    def encode(self, sm):
        n_token = len(sm)
        coded_ids = [None]*n_token
        for i, token in enumerate(sm):
            coded_ids[i] = self.vocab.stoi.get(token, self.vocab.unk_index)
                
        return coded_ids


class TSMDataset(Dataset):

    def __init__(self, corpus_path, vocab, seq_len=203, transform=Randomizer(), is_train=True):
        self.vocab = vocab
        self.seq_len = seq_len
        self.is_train = is_train
        self.transform = transform
        df = pd.read_csv(corpus_path)
        self.data_size = len(df)
        self.firsts = df['first'].values
        self.seconds = df['second'].values

    def __len__(self):
        return self.data_size

    def __getitem__(self, item):
        sm1, (sm2, is_same_label) = self.firsts[item], self.get_random_pair(item)
        # No randomization
        sm1 = self.encode(sm1) # List of IDs
        sm2 = self.encode(sm2) # List of IDs

        # [CLS] tag = SOS tag, [SEP] tag = EOS tag
        sm1 = [self.vocab.sos_index] + sm1 + [self.vocab.eos_index]
        sm2 = sm2 + [self.vocab.eos_index]

        segment_embd = ([1]*len(sm1) + [2]*len(sm2))[:self.seq_len]
        bert_input = (sm1 + sm2)[:self.seq_len]

        padding = [self.vocab.pad_index]*(self.seq_len - len(bert_input))
        bert_input.extend(padding), segment_embd.extend(padding)

        output = {"bert_input": bert_input,
                  "segment_embd": segment_embd,
                  "is_same": is_same_label}

        return {key: torch.tensor(value) for key, value in output.items()}

    def get_random_pair(self, index):
        '''
        function: Find pair molecule. The boolean is_same_label is 1 
          for same and 0 for different molecules.
        '''
        rand = random.random()
        if rand<0.5: # Same molcule
            return self.firsts[index], 1
        else: # Different (but similar) molecule
            return self.seconds[index], 0

    def encode(self, sm):
        n_token = len(sm)
        coded_ids = [None]*n_token
        for i, token in enumerate(sm):
            coded_ids[i] = self.vocab.stoi.get(token, self.vocab.unk_index)
                
        return coded_ids

class MSMDataset(Dataset):

    def __init__(self, corpus_path, vocab, seq_len=220, transform=Randomizer(), is_train=True, rate=0.01):
        self.vocab = vocab
        self.seq_len = seq_len
        self.is_train = is_train
        self.transform = transform
        df = pd.read_csv(corpus_path)
        self.firsts = df['first'].values
        self.data_size = len(self.firsts)
        self.rate = rate

    def __len__(self):
        return self.data_size

    def __getitem__(self, item):
        sm1, sm2 = self.firsts[item], self.firsts[item]
        sm1 = self.transform(sm1) # List
        sm2 = self.transform(sm2) # List
        masked_ids1, ans_ids1 = self.mask(sm1)
        masked_ids2, ans_ids2 = self.mask(sm2)

        # [CLS] tag = SOS tag, [SEP] tag = EOS tag
        masked_ids1 = [self.vocab.sos_index] + masked_ids1 + [self.vocab.eos_index]
        masked_ids2 = masked_ids2 + [self.vocab.eos_index]

        ans_ids1 = [self.vocab.pad_index] + ans_ids1 + [self.vocab.pad_index]
        ans_ids2 = ans_ids2 + [self.vocab.pad_index]

        segment_embd = ([1]*len(masked_ids1) + [2]*len(masked_ids2))[:self.seq_len]
        bert_input = (masked_ids1 + masked_ids2)[:self.seq_len]
        bert_label = (ans_ids1 + ans_ids2)[:self.seq_len]

        padding = [self.vocab.pad_index]*(self.seq_len - len(bert_input))
        bert_input.extend(padding), bert_label.extend(padding), segment_embd.extend(padding)

        output = {"bert_input": bert_input,
                  "bert_label": bert_label,
                  "segment_embd": segment_embd}

        return {key: torch.tensor(value) for key, value in output.items()}

    def mask(self, sm):
        n_token = len(sm)
        masked_ids, ans_ids = [None]*n_token, [None]*n_token
        for i, token in enumerate(sm):
            if self.is_train: # Mask probablistically when training
                prob = random.random()
            else:  # Do not mask when predicting
                prob = 1.0

            if prob > self.rate:
                masked_ids[i] = self.vocab.stoi.get(token, self.vocab.unk_index)
                ans_ids[i] = PAD
            else: # Mask
                prob /= self.rate
                # 80% randomly change token to mask token
                if prob < 0.8:
                    masked_ids[i] = self.vocab.mask_index
                # 10% randomly change token to random token
                elif prob < 0.9:
                    masked_ids[i] = random.randrange(len(self.vocab))

                # 10% randomly change token to current token
                else:
                    masked_ids[i] = self.vocab.stoi.get(token, self.vocab.unk_index)

                ans_ids[i] = self.vocab.stoi.get(token, self.vocab.unk_index)
                
        return masked_ids, ans_ids