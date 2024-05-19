#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
#
# Reference (https://github.com/kan-bayashi/ParallelWaveGAN/)

import os
import torch
import logging
import argparse
import soundfile as sf

from dataloader import SingleDataset
import cupy as cp
from cupyx.scipy.signal import fftconvolve


from models.autoencoder.AudioDec import Generator as generator_audiodec
# from models.vocoder.HiFiGAN import Generator as generator_hifigan
from models.HiFiGAN_Generator import Generator as generator_hifigan
from bin.test import TestGEN

class TestMain(TestGEN):
    def __init__(self, args,):
        super(TestMain, self).__init__(args=args,)
        self.encoder_type = self.encoder_config.get('model_type', 'symAudioDec')
        self.decoder_type = self.decoder_config.get('model_type', 'symAudioDec')
        if self.encoder_config['generator_params']['input_channels'] > 1:
            self.multi_channel = True
        else:
            self.multi_channel = False
    

    # LOAD DATASET
    def load_dataset(self, subset, subset_num):
        # data_path = os.path.join(
        #     self.encoder_config['data']['reverb_path'], 
        #     self.encoder_config['data']['material_path'], 
        #     self.encoder_config['data']['re_path'], 
        #     self.encoder_config['data']['subset'][subset]
        # )
        audio_rs_dir = os.path.join(
             self.config['data']['subset'][subset],self.data_reverb_path)
        audio_material_dir = os.path.join(
             self.config['data']['subset'][subset],self.data_material_path)
        audio_image_dir = os.path.join(
             self.config['data']['subset'][subset],self.data_image_path)
        assert os.path.exists(data_path), f"{data_path} does not exist!"
        self.dataset = SingleDataset(
            files=[audio_rs_dir,audio_material_dir,audio_image_dir],
            query="*.wav",
            load_fn=sf.read,
            return_utt_id=True,
            subset_num=subset_num,
        )
        logging.info(f"The number of utterances = {len(self.dataset)}.")
    
    
    # LOAD MODEL
    def load_encoder(self):
        if self.encoder_type in ['symAudioDec', 'symAudioDecUniv']:
            encoder = generator_audiodec
        else:     
            raise NotImplementedError(f"Encoder {self.encoder_type} is not supported!")
        self.encoder = encoder(**self.encoder_config['generator_params'])
        self.encoder.load_state_dict(
            torch.load(self.encoder_checkpoint, map_location='cpu')['model']['generator'])
        self.encoder = self.encoder.eval().to(self.device)
        logging.info(f"Loaded Encoder from {self.encoder_checkpoint}.")
    
    
    def load_decoder(self):
        if self.decoder_type in ['symAudioDec', 'symAudioDecUniv']:
            decoder = generator_audiodec
        # elif self.decoder_type in ['HiFiGAN', 'UnivNet']:
        #     decoder = generator_hifigan
        else:     
            raise NotImplementedError(f"Decoder {self.decoder_type} is not supported!")
        self.decoder = decoder(**self.decoder_config['generator_params'])
        self.decoder.load_state_dict(
            torch.load(self.decoder_checkpoint, map_location='cpu')['model']['generator'])
        self.decoder = self.decoder.eval().to(self.device)
        logging.info(f"Loaded Decoder from {self.decoder_checkpoint}.")
    

    def encode(self, audio):
        x = torch.tensor(audio, dtype=torch.float).to(self.device)
        if self.multi_channel:
            x = x.transpose(1, 0).unsqueeze(0) # (T, C) -> (1, C, T)
        else:
            x = x.transpose(1, 0).unsqueeze(1) # (T, C) -> (C, 1, T)
        x_speech, x_rir = self.encoder.encoder(x)
        
        z_speech = self.encoder.projector_speech(x_speech)
        zq_speech, _, _ = self.encoder.quantizer_speech(z_speech)

        z_rir = self.encoder.projector_rir(x_rir)
        zq_rir, _, _ = self.encoder.quantizer_rir(z_rir)
        


        return zq_speech, zq_rir
        
    
    def decode(self, zq_speech, zq_rir):
        if self.decoder_type in ['HiFiGAN', 'UnivNet']:
            y_speech = self.decoder.decoder_speech(zq_speech)
            y_rir = self.decoder.decoder_rir(zq_rir)
        else:
            y_speech = self.decoder.decoder_speech(zq_speech)
            y_rir = self.decoder.decoder_rir(zq_rir)
        return y_speech,y_rir
    
    
    # INITIAL FOLDER
    def initial_folder(self, subset, output_name):
        # model name
        encoder = os.path.dirname(self.encoder_checkpoint).split('/')[-1]
        decoder = os.path.dirname(self.decoder_checkpoint).split('/')[-1]
        # model checkpoint
        encoder_checkpoint = os.path.basename(self.encoder_checkpoint).split('steps')[0].split('-')[-1]
        decoder_checkpoint = os.path.basename(self.decoder_checkpoint).split('steps')[0].split('-')[-1]
        testdir = f"{encoder}-{decoder}_{encoder_checkpoint}-{decoder_checkpoint}"
        # testing set
        setdir = self.encoder_config['data']['subset'][subset]
        self.outdir = os.path.join(output_name, testdir, setdir)
        if not os.path.exists(self.outdir):
            os.makedirs(self.outdir, exist_ok=True)    
    

def main():
    """Run testing process."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset", type=str, default="test")
    parser.add_argument("--subset_num", type=int, default=-1)
    parser.add_argument("--encoder", type=str, required=True)
    parser.add_argument("--decoder", type=str, required=True)
    parser.add_argument("--output_dir", type=str, required=True)
    args = parser.parse_args()

    # initial test_main
    test_main = TestMain(args=args)

    # load dataset
    test_main.load_dataset(args.subset, args.subset_num)

    # load model
    test_main.load_encoder()
    test_main.load_decoder()

    # initial folder
    test_main.initial_folder(args.subset, args.output_dir)
    
    # run testing
    test_main.run()
    

if __name__ == "__main__":
    main()