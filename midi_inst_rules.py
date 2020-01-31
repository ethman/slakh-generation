
import json
import pretty_midi as pm

import utils


def apply_midi_rules(instrument, inst_cls):
    """

    :param instrument:
    :return:
    """
    # TODO: not hard code the file path here...
    instrument = pitch_rule(instrument, inst_cls, 'midi_rules/pitch.json')
    return instrument


def pitch_rule(inst, inst_cls, rules_file):
    """

    :param inst:
    :param rules_file:
    :return:
    """
    rules = json.load(open(rules_file, 'r'))
    if inst_cls not in rules.keys():
        return inst

    if not any(r['enabled'] for r in rules[inst_cls]):
        return inst

    for rule in rules[inst_cls]:
        rule_name = rule['rule_name']
        rule_func = utils.get_midi_rule(rule_name)
        inst = rule_func(inst, rule)

    return inst


def min_max_octave(inst, rule):
    """
    Defines a range for instrument.
    Shifts any notes are above the max down an octave,
    and any notes below the min up an octave.
    :param inst:
    :param rule:
    :return:
    """

    min_note = rule['min']
    max_note = rule['max']

    for note in inst.notes:
        while note.pitch < min_note:
            note.pitch += 12

        while note.pitch > max_note:
            note.pitch -= 12

    return inst


def move_note(inst, rule):
    """
    Moves individual notes from a src to a dest.
    :param inst:
    :param rule:
    :return:
    """
    for note_rule in rule['note_rules']:
        src_note = note_rule['old']
        dest_note = note_rule['new']

        for note in inst.notes:
            if note.pitch == src_note:
                note.pitch = dest_note

    return inst


def shift_all_notes(inst, rule):
    """

    :param inst:
    :param rule:
    :return:
    """
    shift = rule['shift']

    inst.notes = [pm.Note(n.velocity, n.pitch + shift, n.start, n.end) for n in inst.notes]
    return inst
