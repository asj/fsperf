import FioResultDecoder
import ResultData
import utils
import json
from timeit import default_timer as timer
from subprocess import Popen, PIPE, DEVNULL

RESULTS_DIR = "results"

class PerfTest:
    name = ""
    command = ""
    need_remount_after_setup = False
    skip_mkfs_and_mount = False

    # Set this if the test does something specific and isn't going to use the
    # configuration options to change how the test is run.
    oneoff = False

    def maybe_cycle_mount(self, mnt):
        if self.need_remount_after_setup:
            mnt.cycle_mount()

    def run(self, run, config, section, results):
        with utils.LatencyTracing(config, section) as lt:
            self.test(run, config, results)
        self.lat_trace = lt
        self.record_results(run)

    def setup(self, config, section):
        pass

    def record_results(self, run):
        raise NotImplementedError

    def test(self, config):
        raise NotImplementedError

    def teardown(self, config, results):
        pass

class FioTest(PerfTest):
    def record_results(self, run):
        json_data = open("{}/{}.json".format(RESULTS_DIR, self.name))
        data = json.load(json_data, cls=FioResultDecoder.FioResultDecoder)
        for j in data['jobs']:
            r = ResultData.FioResult()
            r.load_from_dict(j)
            run.fio_results.append(r)

    def default_cmd(self, results):
        command = "fio --output-format=json"
        command += " --output={}/{}.json".format(RESULTS_DIR, self.name)
        command += " --alloc-size 98304 --allrandrepeat=1 --randseed=12345"
        return command

    def test(self, run, config, results):
        directory = config.get('main', 'directory')
        command = self.default_cmd(results)
        command += " --directory {} ".format(directory)
        command += self.command
        utils.run_command(command)

class TimeTest(PerfTest):
    def record_results(self, run):
        r = ResultData.TimeResult()
        r.elapsed = self.elapsed
        run.time_results.append(r)

    def test(self, run, config, results):
        directory = config.get('main', 'directory')
        command = self.command.replace('DIRECTORY', directory)
        start = timer()
        utils.run_command(command)
        self.elapsed = timer() - start

class DbenchTest(PerfTest):
    def record_results(self, run):
        r = ResultData.DbenchResult()
        r.load_from_dict(self.results)
        run.dbench_results.append(self.results)

    def test(self, run, config, results):
        directory = config.get('main', 'directory')
        command = "dbench " + self.command + " -D {}".format(directory)
        fd = open("{}/{}.txt".format(RESULTS_DIR, self.name), "w+")
        utils.run_command(command, fd)
        fd.seek(0)
        parse = False
        self.results = {}
        for line in fd:
            if not parse:
                if "----" in line:
                    parse = True
                continue
            vals = line.split()
            if len(vals) == 4:
                key = vals[0].lower()
                self.results[key] = vals[3]
            elif len(vals) > 4:
                self.results['throughput'] = vals[1]
