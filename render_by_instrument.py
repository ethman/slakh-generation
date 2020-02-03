#!/usr/bin/sudo python

import os
import sys
import time
import json
import numpy as np
import soundfile as sf
import copy
import yaml
import argparse
import logging
import collections
import shutil
import random

import pretty_midi
import utils
import pyloudnorm as pyln
import midi_inst_rules
from loguru import logger


def select_patch_rand(defs_dict, id_):
    """
    Selects a patch at random
    Args:
        defs_dict:
        id_:

    Returns:

    """
    idx = np.random.randint(0, len(defs_dict[id_]))
    return defs_dict[id_][idx]


def invert_defs_dict(defs_dict):
    """
    Inverts the definitions dictionary such that
    the instrument program numbers are the keys
    and the

    Args:
        defs_dict (dict):

    Returns:

    """
    result = {}

    for v in defs_dict.values():
        for i in v['program_numbers']:
            result[i] = v['defs']

    return result


def make_src_by_inst(defs_dict):

    insts = []
    for v in defs_dict.values():
        for i in v['defs']:
            insts.append(i)

    insts = set(insts)

    return {i: [] for i in insts}


def check_midi_file(midi_path, inst_classes, pgm0_is_piano,
                    band_classes_def=None, separate_drums=False):
    """
    Determines if this MIDI file is okay. Will reject a MIDI file
    if any of the following are true:
        - MIDI file cannot be read
        - The number of unique instruments is less than 2
        - separate_drums is False and there is more than 1 drum track
        - band_classes_def is provided and this file does not have
          the required instruments

    If none of the above are true, the loaded PrettyMIDI object
    will be returned.

    Args:
        midi_path (str): Path to candidate MIDI file.
        inst_classes (dict): Instrument classes/MIDI program numbers and classes.
        pgm0_is_piano (bool): Whether to consider program 0 as piano.
        band_classes_def (dict): (Optional) Band definition dictionary.
        separate_drums (bool): Whether separate drum tracks are okay.

    Returns:
        False if this file fails any of the above checks,
        A loaded PrettyMIDI object otherwise.
    """
    try:
        pm = pretty_midi.PrettyMIDI(midi_path)
    except:
        logger.info('Unable to read {}'.format(midi_path))
        return False

    # Make sure there's more than one instrument
    if len(pm.instruments) < 2:
        return False

    # Make sure there's more than one TYPE of instrument
    unique_inst = len(set([utils.get_inst_class(inst_classes, i, pgm0_is_piano)
                           for i in pm.instruments]))
    if unique_inst == len(pm.instruments):
        # There's only one type of source!
        return False

    # Sometimes a midi file will split out every drum note into a separate track.
    # reject these because it screws with mixing.
    if not separate_drums:
        n_drum_tracks = sum(1 for i in pm.instruments if i.is_drum)
        if n_drum_tracks > 1:
            return False

    # If we're requiring a set of instruments,
    # make sure this file has all the necessary instruments
    if band_classes_def is not None:
        inst_set = set([utils.get_inst_class(inst_classes, i, pgm0_is_piano)
                        for i in pm.instruments])
        if not band_classes_def.issubset(inst_set):
            return False

    # everything looks good
    return pm


def make_zero_based_midi(defs):
    """
    The official MIDI spec is 1 based (why???), but
    clearly most things are 0 based. So this function shifts all of the
    program numbers down by one and keeps 0 as piano.
    :param defs:
    :return:
    """
    for k, v in defs.items():
        pgms = [max(i - 1, 0) for i in v['program_numbers']]
        defs[k]['program_numbers'] = pgms

    return defs


def prepare_midi(midi_paths, max_num_files, output_base_dir, inst_classes, defs_dict,
                 pgm0_is_piano=False, rerender_existing=False, band_classes_def=None,
                 same_pgms_diff=False, separate_drums=False, zero_based_midi=False):
    """
    Loops through a list of `midi_paths` until `max_num_files` have been flagged for
    synthesis. For each file flagged for synthesis, the MIDI file is copied to the
    output directory and each individual track split of into its own MIDI file.
    Each MIDI instrument track is also assigned a synthesis patch.

    Args:
        midi_paths (list): List of paths to MIDI files.
        max_num_files (int): Total number of files to render.
        output_base_dir (str): Base directory where output will be stored.
        inst_classes:
        defs_dict:
        pgm0_is_piano:
        rerender_existing:
        band_classes_def:
        same_pgms_diff:
        separate_drums:
        zero_based_midi:

    Returns:

    """
    midi_files_read = 0
    defs_dict = defs_dict if not zero_based_midi else make_zero_based_midi(defs_dict)
    srcs_by_inst = make_src_by_inst(defs_dict)
    inv_defs_dict = invert_defs_dict(defs_dict)
    for path in midi_paths:
        logger.info('Starting {}'.format(path))

        pm = check_midi_file(path, inst_classes, pgm0_is_piano,
                             band_classes_def, separate_drums)
        if not pm:
            continue

        # Okay, we're all good to continue now
        logger.info('({}/{}) Selected {}'.format(midi_files_read, max_num_files, path))
        midi_files_read += 1

        # Make a whole bunch of paths to store everything
        uuid = os.path.splitext(os.path.basename(path))[0]
        out_dir_name = 'Track{:05d}'.format(midi_files_read)
        output_dir = os.path.join(output_base_dir, out_dir_name)
        utils.safe_make_dirs(output_dir)
        shutil.copy(path, output_dir)
        os.rename(os.path.join(output_dir, uuid + '.mid'),
                  os.path.join(output_dir, 'all_src.mid'))
        midi_out_dir = os.path.join(output_dir, 'MIDI')
        audio_out_dir = os.path.join(output_dir, 'stems')
        utils.safe_make_dirs(midi_out_dir)
        utils.safe_make_dirs(audio_out_dir)

        # Set up metadata
        metadata = {
            'lmd_midi_dir': os.path.sep.join(path.split(os.path.sep)[-6:]),
            'midi_dir': midi_out_dir,
            'audio_dir': audio_out_dir,
            'UUID': uuid
        }
        seen_pgms = {}

        # Loop through instruments in this MIDI file
        for j, inst in enumerate(pm.instruments):

            # Name it and figure out what instrument class this is
            key = 'S{:02d}'.format(j)
            inst_cls = utils.get_inst_class(inst_classes, inst, pgm0_is_piano)

            # Set up metadata
            metadata[key] = {}
            metadata[key]['inst_class'] = inst_cls
            metadata[key]['is_drum'] = inst.is_drum
            metadata[key]['midi_program_name'] = utils.get_inst_program_name(inst_classes,
                                                                             inst, pgm0_is_piano)

            if inst.is_drum:
                # Drums use this special flag, but not the program number,
                # so the pgm # is always set to 0.
                # But usually program number 0 is piano.
                # So we define program number 129/128 for drums to avoid collisions.
                program_num = 129 if not zero_based_midi else 128
            else:
                program_num = int(inst.program)

            metadata[key]['program_num'] = program_num
            metadata[key]['midi_saved'] = False
            metadata[key]['audio_rendered'] = False

            if program_num not in inv_defs_dict or len(inv_defs_dict[program_num]) < 1:
                metadata[key]['plugin_name'] = 'None'
                logger.info('No instrument loaded for \'{}\' (skipping).'.format(inst_cls))
                continue

            # if we've seen this program # before, use the previously selected patch
            if not same_pgms_diff and program_num in seen_pgms.keys():
                selected_patch = seen_pgms[program_num]
            else:
                selected_patch = select_patch_rand(inv_defs_dict, program_num)
                seen_pgms[program_num] = selected_patch

            metadata[key]['plugin_name'] = selected_patch

            # Save the info we need for the next stages
            render_info = {'metadata': os.path.join(output_dir, 'metadata.yaml'),
                           'source_key': key,
                           'end_time': pm.get_end_time() + 5.0}
            srcs_by_inst[selected_patch].append(render_info)

            # Make the output path
            midi_out_path = os.path.join(midi_out_dir, '{}.mid'.format(key))
            if os.path.exists(midi_out_path) and not rerender_existing:
                logger.info('Found {}. Skipping...'.format(midi_out_path))
                continue

            # Save a midi file with just that source
            midi_stem = copy.copy(pm)
            midi_stem.name = key
            midi_stem.instruments = []
            inst = midi_inst_rules.apply_midi_rules(inst, inst_cls)
            midi_stem.instruments.append(inst)
            midi_stem.write(midi_out_path)

            if os.path.isfile(midi_out_path):
                metadata[key]['midi_saved'] = True
                logger.info('Wrote {}.mid. Selected patch \'{}\''.format(key, selected_patch))

        if not rerender_existing:
            with open(os.path.join(output_dir, 'metadata.yaml'), 'w') as f:
                f.write(yaml.safe_dump(metadata, default_flow_style=False, allow_unicode=True))

        logger.info('Finished {}'.format(path))

        if midi_files_read >= max_num_files:
            logger.info('Finished reading MIDI')
            break

    return srcs_by_inst


def render_sources(src_by_inst, sr, buf, kontakt_path, def_dir, dest_dir, sleep=7.0, restart_lim=50,
                   rerender_existing=False):
    """

    Args:
        src_by_inst:
        sr:
        buf:
        kontakt_path:
        def_dir:
        dest_dir:
        sleep:
        restart_lim:
        rerender_existing:

    Returns:

    """

    output_dirs = []
    inst_cnt = 0
    for inst, render_info_list in src_by_inst.items():
        inst_cnt += 1
        if len(render_info_list) == 0:
            continue

        try:
            eng = None
            render_cnt = 0
            for render_info_dict in render_info_list:

                render_cnt += 1
                metadata_path = render_info_dict['metadata']
                source_key = render_info_dict['source_key']
                end_time = render_info_dict['end_time']
                metadata = yaml.load(open(metadata_path, 'r'))

                audio_out_path = os.path.join(metadata['audio_dir'], '{}.wav'.format(source_key))

                if os.path.exists(audio_out_path) and not rerender_existing:
                    logger.info('Found {}. Skipping...'.format(audio_out_path))
                    output_dirs.append(os.path.dirname(audio_out_path))
                    continue

                logger.info('({}/{}) Starting Render '
                            'for MIDI {}, Src {}'.format(render_cnt, len(render_info_list),
                                                         metadata['midi_dir'], source_key))

                if eng is None or render_cnt % restart_lim == 0:
                    del eng

                    if '.nkm' in inst:
                        eng = utils.load_engine_konkakt(sr, buf, str(kontakt_path), def_dir, inst,
                                                        dest_dir, sleep,
                                                        verbose=False)
                    else:
                        eng = utils.load_engine(sr, buf, inst, verbose=False)

                    logger.info('~~({}/{})~~ Loaded RenderMan engine {}'.format(inst_cnt,
                                                                                len(src_by_inst),
                                                                                inst))

                midi_file_path = os.path.abspath(os.path.join(metadata['midi_dir'],
                                                              '{}.mid'.format(source_key)))

                metadata[source_key]['plugin_preset_name'] = eng.get_program_name()

                # Set and save params here
                # _, metadata[source_key]['parameters'] = utils.set_parameters(eng)

                eng.load_midi(str(midi_file_path))
                eng.render_midi(end_time)
                logger.info('Rendered MIDI file...')

                # Do some crude normalization before we write to disk
                audio = np.array(eng.get_audio_frames())
                if np.max(np.abs(audio)) == 0.0:
                    continue

                audio /= np.max(np.abs(audio))
                audio *= 0.8

                if not np.isclose(float(len(audio)) / float(sr), end_time, atol=0.1):
                    raise RuntimeError(
                        'Length of rendered audio ({}) does not match end_time ({})'
                        .format(float(len(audio)) / float(sr), end_time)
                    )

                # Save the audio to disk
                sf.write(audio_out_path, audio, sr)

                if os.path.isfile(audio_out_path):
                    logger.info('Wrote {} to disk'.format(audio_out_path))
                    output_dirs.append(os.path.dirname(audio_out_path))
                    metadata[source_key]['audio_rendered'] = True
                else:
                    logger.warning('Could not write {}!'.format(audio_out_path))

                with open(metadata_path, 'w') as f:
                    f.write(yaml.safe_dump(metadata, default_flow_style=False, allow_unicode=True))

            del eng
        except Exception as e:
            logger.warning('Got exception type {} loading {}. Skipping...'.format(e.message, inst))

    logger.info('Finished rendering audio')
    return list(set(output_dirs))


def normalize_and_mix(output_dirs, sr, normalization_factor, target_peak, remix_existing=False):
    """

    Args:
        output_dirs:
        sr:
        normalization_factor:
        target_peak:
        remix_existing:

    Returns:

    """

    logger.info('Starting mixing...')
    meter = pyln.Meter(sr)
    target_gain = np.power(10.0, target_peak / 20.0)
    for i, cur_dir in enumerate(output_dirs):
        try:
            mix_output_path = os.path.join(os.path.dirname(cur_dir), 'mix.wav')
            if os.path.exists(mix_output_path) and not remix_existing:
                logger.info('Found {}. Skipping'.format(mix_output_path))
                continue

            metadata_path = os.path.join(os.path.dirname(cur_dir), 'metadata.yaml')
            if os.path.isfile(metadata_path):
                metadata = yaml.load(open(metadata_path))
            else:
                metadata = {}
            metadata['normalized'] = False

            logger.info('({}/{}) Mixing {}'.format(i+1, len(output_dirs), cur_dir))

            all_audio = {p: sf.read(os.path.join(cur_dir, p))[0] for p in os.listdir(cur_dir)
                         if os.path.splitext(p)[1] == '.wav'}
            all_audio = collections.OrderedDict(all_audio)
            loudnesses = [meter.integrated_loudness(a) for a in all_audio.values()]

            for j, n, in enumerate(all_audio.keys()):
                k = os.path.splitext(n)[0]
                if k not in metadata:
                    metadata[k] = {}
                metadata[k]['integrated_loudness'] = float(loudnesses[j])

            if np.any(np.isinf(loudnesses)):
                raise RuntimeError('One or more sources have -inf loudness!')

            normalized_audio = {p: pyln.normalize.loudness(a, loudnesses[j], normalization_factor)
                                for j, (p, a) in enumerate(all_audio.items())}
            mixture = np.sum(normalized_audio.values(), axis=0)

            peak = np.max(np.abs(mixture))
            if peak >= target_gain:
                gain = target_gain / peak
                mixture *= gain

                if np.any(np.isnan(mixture)):
                    raise RuntimeError('This mixture contains NaNs!!!')

                normalized_audio = {p: a * gain for p, a in normalized_audio.items()}

                metadata['overall_gain'] = float(gain)

            else:
                metadata['overall_gain'] = 1.0

            _ = [sf.write(os.path.join(cur_dir, p), a, sr) for p, a in normalized_audio.items()]
            sf.write(mix_output_path, mixture, sr)

            metadata['normalization_factor'] = normalization_factor
            metadata['target_peak'] = target_peak
            metadata['normalized'] = True

            with open(metadata_path, 'w') as f:
                f.write(yaml.safe_dump(metadata, default_flow_style=False, allow_unicode=True))

        except Exception as e:
            logger.warning('Trouble mixing {}. Exception: {} Skipping...'.format(cur_dir,
                                                                                 e.message))


def run(config_file_path):
    config = json.load(open(config_file_path, 'r'))
    logfile = config['logfile_basename'] + '_{time}.log'
    logger.add(logfile, format="{time} | {level} | {message}", level="INFO")

    start = time.time()
    logger.info('Using config file: {}, with settings as follows...'.format(config_file_path))
    logger.info('~' * 50)
    logger.info('Parameters:')
    for k, v in config.items():
        logger.info('{}: {}'.format(k, v))
    logger.info('~' * 50)
    logger.info('Starting script...')

    lmd_base_dir = config['lmd_base_dir']
    np.random.seed(config['random_seed'])
    random.seed(config['random_seed'])
    max_num_files = config['max_num_files']
    output_dir = config['output_dir']

    logger.info('Reading MIDI file paths')
    if config['midi_file_list'] is not None:
        with open(config['midi_file_list']) as f:
            midi_file_paths = f.read().splitlines()
        logger.info('Read midi file list from {}'.format(config['midi_file_list']))
    else:
        midi_file_paths = [os.path.join(root, name)
                           for root, dirs, files in os.walk(lmd_base_dir)
                           for name in files if os.path.splitext(name)[1] == '.mid']
        logger.info('Traversed LMD directory structure.')
    np.random.shuffle(midi_file_paths)

    inst_classes = json.load(open(config['instrument_classes_file'], 'r'))
    defs_dict = json.load(open(config['defs_metadata_file'], 'r'))
    band_definition = None
    if config['band_definition_file']:
        band_definition = set(json.load(open(config['band_definition_file'], 'r'))['band_def'])

    src_by_inst = prepare_midi(
        midi_file_paths,
        max_num_files,
        output_dir,
        inst_classes,
        defs_dict,
        pgm0_is_piano=config['render_pgm0_as_piano'],
        band_classes_def=band_definition,
        rerender_existing=config['rerender_existing'],
        separate_drums=config['separate_drums'],
        zero_based_midi=config['zero_based_midi']
    )
    logger.info('All done with MIDI ({} secs elapsed). '
                'Onto RenderMan...'.format(time.time() - start))

    output_dirs = render_sources(
        src_by_inst,
        config['renderman_sr'],
        config['renderman_buf'],
        config['kontakt_path'],
        config['user_defs_dir'],
        config['kontakt_defs_dir'],
        sleep=config['renderman_sleep'],
        rerender_existing=config['rerender_existing']
    )
    logger.info('Done with RenderMan ({} secs elapsed). '
                'Onto mixing...'.format(time.time() - start))

    normalize_and_mix(
        output_dirs,
        config['renderman_sr'],
        config['mix_normalization_factor'],
        config['mix_target_peak'],
        remix_existing=True
    )
    dur = time.time() - start
    logger.info('Finished {} files in {} seconds'.format(max_num_files, dur))
    logger.info('Output audio is at {}'.format(output_dir))
    logger.info('Bye!')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config-file', type=str, help='Config file for rendering the audio')
    args = parser.parse_args()
    run(args.config_file)
