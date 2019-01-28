# -*- coding: utf-8 -*-
"""Tests for google3.third_party.car.hw.testing.output.email."""

import io
import json
import logging
import os
import unittest

from openhtf.core import measurements
from openhtf.core import test_record
from openhtf.util import logs as test_logs
from openhtf.util import units

import openhtf as htf
from openhtf import util
from examples import all_the_things
from openhtf.output.callbacks import console_summary
from openhtf.output.callbacks import json_factory
from openhtf.output.proto import assembly_event_pb2
from openhtf.output.proto import mfg_event_converter
from openhtf.output.proto import mfg_event_pb2
from openhtf.output.proto import test_runs_converter
from openhtf.output.proto import test_runs_pb2


TEST_MULTIDIM_JSON_FILE = os.path.join(
    os.path.dirname(__file__),
    'multidim_testdata.json')
with io.open(TEST_MULTIDIM_JSON_FILE, 'r', encoding='utf-8') as f:
  TEST_MULTIDIM_JSON = f.read()

class MfgEventConverterTest(unittest.TestCase):

  def create_codeinfo(self):
    return test_record.CodeInfo(
        name='mock-codeinfo-name',
        docstring='mock-docstring',
        sourcecode='mock-sourcecode',
    )

  def test_mfg_event_from_test_record(self):
    """Test for the full conversion flow."""
    record = test_record.TestRecord(
        dut_id='dut_serial',
        start_time_millis=1,
        end_time_millis=1,
        station_id='localhost',
        outcome=test_record.Outcome.PASS,
    )
    record.outcome = test_record.Outcome.PASS
    record.metadata = {
        'assembly_events': [assembly_event_pb2.AssemblyEvent()] * 2,
        'config': {'mock-config-key': 'mock-config-value'},
        'operator_name': 'mock-operator-name',
    }
    record.phases = [
        test_record.PhaseRecord(
            name='phase-%d' % idx, descriptor_id=idx,
            codeinfo=test_record.CodeInfo.uncaptured(),
            result=None, attachments={},
            start_time_millis=1, end_time_millis=1)
        for idx in range(1, 5)
    ]
    for phase in record.phases:
      phase.measurements = {
          'meas-1': measurements.Measurement('meas-1'),
          'meas-2': measurements.Measurement('meas-2'),
          'meas-3': measurements.Measurement('meas-3').with_dimensions('V'),
      }
      phase.attachments = {
          'attach-1': test_record.Attachment(data='data-1', mimetype=''),
          'attach-2': test_record.Attachment(data='data-2', mimetype=''),
      }

    mfg_event = mfg_event_converter.mfg_event_from_test_record(record)

    self.assertEqual(mfg_event.dut_serial, record.dut_id)
    self.assertEqual(len(mfg_event.assembly_events), 2)
    self.assertEqual(len(mfg_event.measurement), 8)
    self.assertEqual(sorted(m.name for m in mfg_event.measurement),
                     ['meas-1_0', 'meas-1_1', 'meas-1_2', 'meas-1_3',
                      'meas-2_0', 'meas-2_1', 'meas-2_2', 'meas-2_3'])
    self.assertEqual(len(mfg_event.attachment), 15)
    self.assertEqual(sorted(str(m.name) for m in mfg_event.attachment),
                     ['OpenHTF_record.json', 'argv',
                      'attach-1_0', 'attach-1_1', 'attach-1_2', 'attach-1_3',
                      'attach-2_0', 'attach-2_1', 'attach-2_2', 'attach-2_3',
                      'config',
                      'multidim_meas-3_0', 'multidim_meas-3_1',
                      'multidim_meas-3_2', 'multidim_meas-3_3'])


  def test_populate_basic_data(self):
    outcome_details = test_record.OutcomeDetails(
        code='mock-code',
        description='mock-description',
    )
    phase = test_record.PhaseRecord(
        name='mock-phase-name',
        descriptor_id=1,
        codeinfo=self.create_codeinfo(),
        start_time_millis=200,
        end_time_millis=400,
    )
    log_record = test_logs.LogRecord(
        level=logging.INFO,
        logger_name='mock-logger-name',
        source='mock-source',
        lineno=123,
        timestamp_millis=300,
        message='mock-message',
    )
    record = test_record.TestRecord(
        dut_id='mock-dut-id',
        station_id='mock-station-id',
        start_time_millis=100,
        end_time_millis=500,
        outcome=test_record.Outcome.PASS,
        outcome_details=[outcome_details],
        metadata={
            'test_name': 'mock-test-name',
            'operator_name': 'mock-operator-name',
            'test_version': 1.0,
            'test_description': 'mock-test-description',
        },
        phases=[phase],
        log_records=[log_record],
    )

    mfg_event = mfg_event_pb2.MfgEvent()
    mfg_event_converter._populate_basic_data(mfg_event, record)

    self.assertEqual(mfg_event.dut_serial, 'mock-dut-id')
    self.assertEqual(mfg_event.start_time_ms, 100)
    self.assertEqual(mfg_event.end_time_ms, 500)
    self.assertEqual(mfg_event.tester_name, 'mock-station-id')
    self.assertEqual(mfg_event.test_name, 'mock-test-name')
    self.assertEqual(mfg_event.test_version, '1.0')
    self.assertEqual(mfg_event.test_description, 'mock-test-description')
    self.assertEqual(mfg_event.test_status, test_runs_pb2.PASS)

    # Phases.
    self.assertEqual(mfg_event.phases[0].name, 'mock-phase-name')
    self.assertEqual(mfg_event.phases[0].description, 'mock-sourcecode')
    self.assertEqual(mfg_event.phases[0].timing.start_time_millis, 200)
    self.assertEqual(mfg_event.phases[0].timing.end_time_millis, 400)

    # Failure codes.
    self.assertEqual(mfg_event.failure_codes[0].code, 'mock-code')
    self.assertEqual(mfg_event.failure_codes[0].details, 'mock-description')

    # Test logs.
    self.assertEqual(mfg_event.test_logs[0].timestamp_millis, 300)
    self.assertEqual(mfg_event.test_logs[0].log_message, 'mock-message')
    self.assertEqual(mfg_event.test_logs[0].logger_name, 'mock-logger-name')
    self.assertEqual(mfg_event.test_logs[0].levelno, logging.INFO)
    self.assertEqual(mfg_event.test_logs[0].level,
                     test_runs_pb2.TestRunLogMessage.INFO)
    self.assertEqual(mfg_event.test_logs[0].log_source, 'mock-source')
    self.assertEqual(mfg_event.test_logs[0].lineno, 123)

  def test_attach_record_as_json(self):
    record = test_record.TestRecord('mock-dut-id', 'mock-station-id')
    mfg_event = mfg_event_pb2.MfgEvent()
    mfg_event_converter._attach_record_as_json(mfg_event, record)

    self.assertEqual(mfg_event.attachment[0].name, 'OpenHTF_record.json')
    self.assertTrue(mfg_event.attachment[0].value_binary)  # Assert truthy.
    self.assertEqual(mfg_event.attachment[0].type, test_runs_pb2.TEXT_UTF8)

  def test_attach_config(self):
    record = test_record.TestRecord('mock-dut-id', 'mock-station-id',
                                    metadata={'config': {'key': 'value'}})
    mfg_event = mfg_event_pb2.MfgEvent()
    mfg_event_converter._attach_config(mfg_event, record)

    self.assertEqual(mfg_event.attachment[0].name, 'config')
    self.assertTrue(mfg_event.attachment[0].value_binary)  # Assert truthy.
    self.assertEqual(mfg_event.attachment[0].type, test_runs_pb2.TEXT_UTF8)

  def _create_and_set_measurement(self, name, value):
    measured_value = measurements.MeasuredValue(name, is_value_set=False)
    measured_value.set(value)

    measurement = measurements.Measurement(
        name=name, outcome=measurements.Outcome.PASS)
    # Cannot be set in initialization.
    measurement.measured_value = measured_value
    return measurement

  def test_copy_measurements_from_phase(self):
    measurement = (
        self._create_and_set_measurement('mock-measurement-name', 5).
        doc('mock measurement docstring').
        with_units(units.Unit('radian')).
        in_range(1, 10))

    # We 'incorrectly' create a measurement with a unicode character as
    # a python2 string.  We don't want mfg_event_converter to guess at it's
    # encoding but we also don't want to fail after a test on conversion so it
    # replaces errors with a unicode question mark character.
    measurement_text = self._create_and_set_measurement('text', b'\xfd')
    measurement_unicode = self._create_and_set_measurement('unicode', u'\ufffa')

    phase = test_record.PhaseRecord(
        name='mock-phase-name',
        descriptor_id=1,
        codeinfo=self.create_codeinfo(),
        measurements={
            'mock-measurement-name': measurement,
            'text': measurement_text,
            'unicode': measurement_unicode,
        },
    )

    mfg_event = mfg_event_pb2.MfgEvent()
    copier = mfg_event_converter.PhaseCopier([phase])
    copier.copy_measurements(mfg_event)

    # Names.
    created_measurements = sorted(mfg_event.measurement, key=lambda m: m.name)
    mock_measurement = created_measurements[0]
    text_measurement = created_measurements[1]
    unicode_measurement = created_measurements[2]
    self.assertEqual(mock_measurement.name, u'mock-measurement-name')
    self.assertEqual(text_measurement.name, u'text')
    self.assertEqual(unicode_measurement.name, u'unicode')

    # Basic measurement fields.
    self.assertEqual(mock_measurement.status, test_runs_pb2.PASS)
    self.assertEqual(mock_measurement.description, 'mock measurement docstring')
    self.assertEqual(mock_measurement.parameter_tag[0], 'mock-phase-name')
    self.assertEqual(mock_measurement.unit_code,
                     test_runs_pb2.Units.UnitCode.Value('RADIAN'))

    # Measurement value.
    self.assertEqual(mock_measurement.numeric_value, 5.0)
    # FFFD is unicode's '?'.  This occurs when we can't easily convert a python2
    # string to unicode.
    self.assertEqual(text_measurement.text_value, u'\ufffd')
    self.assertEqual(unicode_measurement.text_value, u'\ufffa')

    # Measurement validators.
    self.assertEqual(mock_measurement.numeric_minimum, 1.0)
    self.assertEqual(mock_measurement.numeric_maximum, 10.0)
    self.assertEqual(mock_measurement.name, u'mock-measurement-name')
    self.assertEqual(mock_measurement.name, u'mock-measurement-name')

  def testCopyAttachmentsFromPhase(self):
    attachment = test_record.Attachment('mock-data', 'text/plain')
    phase = test_record.PhaseRecord(
        name='mock-phase-name',
        descriptor_id=1,
        codeinfo=self.create_codeinfo(),
        attachments={'mock-attachment-name': attachment},
    )

    mfg_event = mfg_event_pb2.MfgEvent()
    copier = mfg_event_converter.PhaseCopier([phase])
    copier.copy_attachments(mfg_event)

    self.assertEqual(mfg_event.attachment[0].name, 'mock-attachment-name')
    self.assertEqual(mfg_event.attachment[0].value_binary, b'mock-data')
    self.assertEqual(mfg_event.attachment[0].type, test_runs_pb2.TEXT_UTF8)


class MultiDimConversionTest(unittest.TestCase):

  @classmethod
  def create_multi_dim_measurement(cls):
    """Util function to create a test multi-dim measurement."""
    measurement = measurements.Measurement('test_measurement')
    measurement.with_units('°C').with_dimensions('ms', 'assembly', 'zone')
    for t in range(10):
      for assembly in ['A', 'B', 'C']:
        for zone in range(3):
          temp = zone + t
          dims = (t, assembly, zone)
          measurement.measured_value[dims] = temp

    measurement.outcome = measurements.Outcome.PASS

    return measurement

  def test_multidim_measurement_to_attachment(self):
    """Test for the full conversion flow."""
    meas = self.create_multi_dim_measurement()

    attachment = mfg_event_converter.multidim_measurement_to_attachment(
        name='test_measurement_multidim', measurement=meas)

    self.assertEqual(
        json.loads(TEST_MULTIDIM_JSON), json.loads(attachment.data))

  def test_attachment_to_multidim_measurement(self):
    expected = self.create_multi_dim_measurement()

    attachment = test_record.Attachment(TEST_MULTIDIM_JSON,
                                        test_runs_pb2.MULTIDIM_JSON)
    measurement = mfg_event_converter.attachment_to_multidim_measurement(
        attachment)

    self.assertEqual(expected.measured_value.value,
                     measurement.measured_value.value)
    for exp, act in zip(expected.dimensions, measurement.dimensions):
      self.assertEqual(exp, act)

  def test_reversibleish(self):
    """Verify that in happy case multidim -> attachment is reversible."""
    mdim = self.create_multi_dim_measurement()

    attachment = mfg_event_converter.multidim_measurement_to_attachment(
        name='test_measurement_multidim', measurement=mdim)

    reversed_mdim = mfg_event_converter.attachment_to_multidim_measurement(
        attachment)

    self.assert_same_mdim(mdim, reversed_mdim)

  def test_reversibleish_leagcy_status_int(self):
    """Verfiy multidim -> attachment is reversible even on leagacy data.

    Older implementations would cast the outcome to an int instead of a string.
    We verify we can cast the saved int into correct outcome.
    """
    mdim = self.create_multi_dim_measurement()

    attachment = mfg_event_converter.multidim_measurement_to_attachment(
        name='test_measurement_multidim', measurement=mdim)

    # Re-parse the data, edit the outcome field to a int, then reserialize.
    data_dict = json.loads(attachment.data)
    data_dict['outcome'] = test_runs_pb2.Status.Value(data_dict['outcome'])
    attachment = test_record.Attachment(json.dumps(data_dict),
                                        test_runs_pb2.MULTIDIM_JSON)


    reversed_mdim = mfg_event_converter.attachment_to_multidim_measurement(
        attachment)

    self.assert_same_mdim(mdim, reversed_mdim)

  def assert_same_mdim(self, expected, other):
    self.assertEqual(expected.outcome, other.outcome)
    self.assertEqual(expected.units, other.units)
    self.assertEqual(expected.dimensions, other.dimensions)

    self.assertEqual(
      len(expected.measured_value.value_dict),
      len(other.measured_value.value_dict),
      )
    for k, v in expected.measured_value.value_dict.items():
      assert k in other.measured_value.value_dict, (
        'expected key %s is not present in other multidim' % k)
      other_v = other.measured_value.value_dict[k]
      self.assertEqual(v, other_v, 'Different values for key: %s (%s != %s)' % (
        k, v, other_v))