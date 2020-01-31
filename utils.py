import os
import sys
import shutil
import numpy as np
import time
import errno
import soundfile as sf
import flac_converter

try:
    sys.path.append(os.path.join('RenderMan-master', 'Builds', 'MacOSX', 'build', 'Debug'))

    import librenderman as rm
except ImportError:
    pass


def copy_and_rename_def(src_dir, src_file, dest_dir):
    """

    :param src_dir:
    :param src_file:
    :param dest_dir:
    :return:
    """
    src_path = os.path.join(src_dir, src_file)
    temp_path = os.path.join(src_dir, 'kontakt_def.nkm')  # The file has to be renamed
    shutil.copy(src_path, temp_path)
    shutil.copy(temp_path, dest_dir)


def get_inst_class(inst_classes, inst, pgm0_is_piano=False):
    """

    :param inst_classes:
    :param inst:
    :param pgm0_is_piano:
    :return:
    """
    if inst.is_drum:
        return u'Drums'

    if inst.program == 0:
        return inst_classes['0']['class'] if pgm0_is_piano else u'Unknown'

    return inst_classes[str(inst.program)]['class']


def get_inst_program_name(inst_classes, inst, pgm0_is_piano=False):
    """

    :param inst_classes:
    :param inst:
    :param pgm0_is_piano:
    :return:
    """
    if inst.is_drum:
        return u'Drums'

    if inst.program == 0:
        return inst_classes['0']['name'] if pgm0_is_piano else u'Unknown'

    return inst_classes[str(inst.program)]['name']


def select_plugin(engine_dict, inst_class):
    """
    Chooses which Renderman Engine (& thus plugin) randomly
    :param engine_dict:
    :param inst_class:
    :return:
    """

    idx = np.random.randint(0, len(engine_dict[inst_class]))
    return engine_dict[inst_class].values()[idx], engine_dict[inst_class].keys()[idx]


def parse_parameter_names(param_str, program_name):
    result = {}
    suf = ' - ' + program_name
    for s in param_str.split('\n'):
        if not s:
            continue

        # idx, name, text = s.split(', ')
        idx, name = s.split(', ')

        if '#' in name or suf not in name:
            # '#' means the parameter is not used and
            # if the suffix is not in the name, then
            # the parameter is for another instrument.
            continue

        idx = int(idx)
        name = name.rsplit(' - ')[0]  # TODO: use program name suffix
        result[idx] = name

    return result


def set_parameters(eng):
    parameter_names = parse_parameter_names(eng.get_plugin_parameters_description(),
                                            eng.get_program_name())

    params = {}
    for idx, name in parameter_names.items():
        val = np.random.rand()
        eng.set_parameter(idx, val)
        params[idx] = {'name': name, 'value': val}

    return eng, params


def load_engine(sr, buf, plugin_path, sleep=7.0, verbose=True):
    """

    :param sr:
    :param buf:
    :param plugin_path:
    :param preset:
    :param sleep:
    :param verbose:
    :return:
    """
    eng = rm.RenderEngine(sr, buf)
    assert eng.load_plugin(str(plugin_path))

    # Set parameters like so:
    # eng.set_parameter(90, 0.5)

    time.sleep(sleep)
    return eng


def load_engine_konkakt(sr, buf, plugin_path, def_dir, def_name, dest_dir, sleep=7.0, verbose=True):
    """

    :param sr: Sample rate to render audio
    :param buf: Buffer size (in samples) for rendering frames
    :param plugin_path: Absolute path to Kontakt.vst or Kontakt.component (AU)
    :param def_dir: Absolute path to the Konkakt defaults directory
    :param def_name: Default Kontakt .nkm file to load Kontakt with a state
    :param sleep: Sleeps for the specified amount of time. Sometimes Kontakt takes some
        time to load all of the samples.
    :return: RenderMan engine that has Konkakt plugin loaded with state provided by def_name
    """
    copy_and_rename_def(def_dir, def_name, dest_dir)
    eng = rm.RenderEngine(sr, buf)
    assert eng.load_plugin(plugin_path)
    if verbose:
        print('Loaded {}'.format(def_name))
    time.sleep(sleep)
    return eng


def safe_make_dirs(path):
    """
    Safe way to make dirs. If the dirs exist, will ignore that error.
    :param path:
    :return:
    """

    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise exc


def get_midi_rule(name):
    import midi_inst_rules, inspect
    return dict(inspect.getmembers(midi_inst_rules, inspect.isfunction))[name]


def make_output_dir(output_base_path, midi_path):
    """
    Output directories mirror the LMD directories. Except every midi file
    in LMD is instead a folder that has all of the sources and metadata.
    :param output_base_path:
    :param midi_path:
    :return:
    """
    dirs = midi_path.split(os.sep)[-5:]  # get the last 4 directories and midi file name
    dirs[-1] = os.path.splitext(dirs[-1])[0]  # remove the extension from the file name
    dirs = os.sep.join(dirs)
    result = os.path.join(output_base_path, dirs)
    safe_make_dirs(result)
    return result


def file_ready_string(string):
    """
    Change a string from 'Something Like This" to "something_like_this"
    for ease of saving it as a filename or directory name.
    :param string:
    :return:
    """
    return string.replace(' ', '_').lower()


def read_audio_file(path):
    if os.path.splitext(path)[1] == '.wav':
        return sf.read(path)
    elif os.path.splitext(path)[1] == '.flac':
        return flac_converter.read_flac_to_numpy(path)
