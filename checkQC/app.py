
import sys
import json
import logging
from pathlib import Path

import click

from checkQC.qc_engine import QCEngine
from checkQC.config import ConfigFactory
from checkQC.run_type_recognizer import RunTypeRecognizer
from checkQC.run_type_summarizer import RunTypeSummarizer
from checkQC.exceptions import CheckQCException, RunfolderNotFoundError
from checkQC import __version__ as checkqc_version


logging.basicConfig(level=logging.DEBUG,
                    format='%(levelname)-8s %(message)s')

console_log_handler = logging.StreamHandler()
log = logging.getLogger("")


@click.command("checkqc")
@click.option("--config", help="Path to the checkQC configuration file", type=click.Path())
@click.option('--json', is_flag=True, default=False, help="Print the results of the run as json to stdout")
@click.version_option(checkqc_version)
@click.argument('runfolder', type=click.Path())
def start(config, json, runfolder):
    """
    checkQC is a command line utility designed to quickly gather and assess quality control metrics from an
    Illumina sequencing run. It is highly customizable and which quality controls modules should be run
    for a particular run type should be specified in the provided configuration file.
    """
    # -----------------------------------
    # This is the application entry point
    # -----------------------------------
    app = App(runfolder, config, json)
    app.run()
    sys.exit(app.exit_status)


class App(object):
    """
    This is the main application object for CheckQC.
    """

    def __init__(self, runfolder, config_file=None, json_mode=False):
        self._runfolder = runfolder
        self._config_file = config_file
        self._json_mode = json_mode
        self.exit_status = 0

    def configure_and_run(self):
        """
        Configures and runs the application. It will set the exit status of the object in accordance with if any
        fatal qc errors were found or not.

        :returns: The reports of the application as a dict
        """
        config = ConfigFactory.from_config_path(self._config_file)
        parser_configurations = config.get("parser_configurations", None)

        if not Path(self._runfolder).is_dir():
            raise RunfolderNotFoundError("Could not find runfolder: {}. Are you "
                                         "sure the path is correct?".format(self._runfolder))

        run_type_recognizer = RunTypeRecognizer(runfolder=self._runfolder)
        instrument_and_reagent_version = run_type_recognizer.instrument_and_reagent_version()

        # TODO For now assume symmetric read lengths
        both_read_lengths = run_type_recognizer.read_length()
        read_length = int(both_read_lengths.split("-")[0])
        handler_config = config.get_handler_configs(instrument_and_reagent_version, read_length)

        run_type_summary = RunTypeSummarizer.summarize(instrument_and_reagent_version, both_read_lengths, handler_config)

        qc_engine = QCEngine(runfolder=self._runfolder,
                             parser_configurations=parser_configurations,
                             handler_config=handler_config)
        reports = qc_engine.run()
        reports["run_summary"] = run_type_summary
        self.exit_status = qc_engine.exit_status
        return reports

    def run(self):
        """
        This method will run CheckQC as it is intended to run as a commandline application, it will log to the
        stderr and write data to stdout.

        :returns: the exit status of the run (0 for success, else not 0)
        """
        log.info("------------------------")
        log.info("Starting checkQC ({})".format(checkqc_version))
        log.info("------------------------")
        log.info("Runfolder is: {}".format(self._runfolder))
        try:
            reports = self.configure_and_run()
            if self.exit_status == 0:
                log.info("Finished without finding any fatal qc errors.")
            else:
                log.error("Finished with fatal qc errors and will exit with non-zero exit status.")

            if self._json_mode:
                print(json.dumps(reports))

        except CheckQCException as e:
            log.error(e)
            self.exit_status

        return self.exit_status

if __name__ == '__main__':
    start()
