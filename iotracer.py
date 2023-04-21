import re
import click
import subprocess
import fnmatch
import pandas
from matplotlib import pyplot as plt, colors as mcolors
from collections import namedtuple
from enum import Enum
import datetime
import svgwrite
from colour import Color

Line = namedtuple('Line', ['start_time', 'syscall',
                  'args', 'return_code', 'duration'])


class Action:
    path_to_height = {}

    def __init__(self, path, start_time, end_time, action) -> None:
        self.path = path
        self.start_time = start_time
        self.end_time = end_time
        self.action = action

        Action.path_to_height.setdefault(self.path, max(list(Action.path_to_height.values()) or [10]) + 30)

        self.color = Color('white')
        self.edgecolor = Color('black')

    @property
    def height(self):
        return Action.path_to_height[self.path]
    
    @property
    def duration(self):
        return self.end_time - self.start_time


STRACE_FLAGS = '-tttTf --decode-fds=path'
STRACE_REG = re.compile(
    r'(?P<start_time>[\d\.]+) (?P<syscall>\w+)\((?P<args>.*)\)\ += (?P<return_code>(?:-?\d+|0x[0-9a-f]+|\?))(?P<decoded_info>\<.*?\>)? (?:.* )?\<(?P<duration>[\d\.]+)\>')
DECODED_INFO_REG = re.compile('(?P<arg>.*)\<(?P<decoded>.*?)\>')


class SYSCALL:
    OPEN = ['open', 'openat']
    CLOSE = ['close']
    READ = ['read']
    WRITE = ['write']


class ACTIONS(Enum):
    OPEN_CLOSE = {'stroke': Color('black'), 'fill': Color(
        'white'), 'fill-opacity': 0, 'stroke-width': 0.1}
    READ = {'stroke': Color('lightgreen'), 'fill': Color(
        'lightgreen'), 'fill-opacity': 0.5, 'stroke-width': 0.1}
    WRITE = {'stroke': Color('lightblue'), 'fill': Color(
        'lightblue'), 'fill-opacity': 0.5, 'stroke-width': 0.1}


def run_strace_command(command):
    p = subprocess.run(f'strace {STRACE_FLAGS} {command}'.split(
        ' '), capture_output=True)
    return p.stderr.decode('utf-8')


def attach_strace_to_process(pid):
    p = subprocess.run(
        f'strace {STRACE_FLAGS} -p {pid}'.split(' '), capture_output=True)
    return p.stderr.decode('utf-8')


def _parse_strace_line(line):
    match = STRACE_REG.match(line)
    if match:
        start_time, syscall, args, return_code, decoded_info, duration = match.groups()
        return Line(
            float(start_time),
            syscall,
            list(map(lambda x: x.strip(), args.split(','))),
            int(return_code, 16 if 'x' in return_code else 10),
            float(duration)
        )


def parse_strace(stderr, paths):
    syscalls = []
    fds = {}

    for line in stderr.splitlines():
        line = _parse_strace_line(line)
        if not line:
            continue

        if line.syscall in SYSCALL.OPEN:
            path = line.args[1].strip('"')
            fds[int(line.return_code)] = {
                'start_time': line.start_time, 'path': path, 'duration': line.duration}

        elif line.syscall in SYSCALL.CLOSE:
            fd, path = DECODED_INFO_REG.match(line.args[0]).groups()
            fd = int(fd)
            if fd not in [1, 2]:
                file_ = fds.pop(fd, {
                    'start_time': None,
                    'path': path,
                    'duration': None
                })
                if any(fnmatch.fnmatch(file_['path'], p) for p in paths):
                    syscalls.append(
                        Action(
                            file_['path'],
                            file_['start_time'],
                            line.start_time + line.duration,
                            ACTIONS.OPEN_CLOSE.name
                        )
                    )

        elif line.syscall in SYSCALL.READ:
            fd, path = DECODED_INFO_REG.match(line.args[0]).groups()
            fd = int(fd)
            file_ = fds.get(
                fd, {'start_time': None, 'path': path, 'duration': None})
            if any(fnmatch.fnmatch(file_['path'], p) for p in paths):
                syscalls.append(
                    Action(
                        file_['path'],
                        line.start_time,
                        line.start_time + line.duration,
                        ACTIONS.READ.name
                    )
                )

        elif line.syscall in SYSCALL.WRITE:
            fd, path = DECODED_INFO_REG.match(line.args[0]).groups()
            fd = int(fd)
            file_ = fds.get(
                fd, {'start_time': None, 'path': path, 'duration': None})
            if any(fnmatch.fnmatch(file_['path'], p) for p in paths):
                syscalls.append(
                    Action(
                        file_['path'],
                        line.start_time,
                        line.start_time + line.duration,
                        ACTIONS.WRITE.name
                    )
                )

    return syscalls


# TODO: fix generage_svg accordingly!!!
def generate_svg(strace_results, keep_timestamps):
    start_time = min(x.start_time for x in strace_results if x.start_time)
    if not keep_timestamps:
        for l in strace_results:
            if l.start_time:
                l.start_time = l.start_time - start_time
            else:
                l.start_time = 0
            l.end_time = l.end_time - start_time

    dwg = svgwrite.Drawing()
    for res in strace_results:
        dwg.add(svgwrite.text.Text(res.path, (5, res.height + 15)))
        dwg.add(svgwrite.shapes.Rect(
            (res.start_time, res.height),
            (res.duration, 20),
            style=";".join(f"{k}:{v}" for k, v in ACTIONS[res.action].value.items())
        ))

    print(dwg.tostring())

    # for l in strace_results:
    #     l.edgecolor = ACTIONS[l.type].value[0]
    #     l.color = ACTIONS[l.type].value[1]

    # df = pandas.DataFrame.from_dict(strace_results)

    # # Create graph
    # fig, ax = plt.subplots()

    # ax.barh(df['path'], df['end_time'] - df['start_time'],
    #         left=df['start_time'], edgecolor=df['edgecolor'], color=df['color'])

    # ax.set_xlim((min(df['start_time']), max(df['end_time'])))

    # mng = plt.get_current_fig_manager()
    # mng.window.maximize()

    # fig.tight_layout()

    # plt.show()


def view_results(svg_path):
    pass


@click.command
@click.option('--path', '-p', 'paths', help="Paths to follow", multiple=True, type=click.Path(), required=False)
@click.option('--strace', '-s', 'strace', help="Parse strace instead of running command", multiple=False, type=click.Path(), required=False)
@click.option('--attach', '--pid', '-a', 'pid', help="Attach to running process", multiple=False, type=int, required=False)
@click.option('--command', '--cmd', '-c', 'command', help="The command to execute and analyze", multiple=False, type=str, required=False)
@click.option('--keep-timestamps', 'keep_timestamps', help="Keep the timestamps", is_flag=True)
def main(command, paths, strace, pid, keep_timestamps):
    if not paths:
        paths = ("*",)

    if strace:
        stderr = open(strace, 'r').read()
    else:
        if pid and command:
            print('cannot run with both pid and command options')
            return
        if not pid and not command:
            print('required either strace, pid or command')
            return
        if pid:
            stderr = attach_strace_to_process(pid)
        else:
            stderr = run_strace_command(command)
        with open(fr'./iotracer.strace-{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}', 'w') as output_file:
            output_file.write(stderr)
    strace_results = parse_strace(stderr, paths)
    svg_path = generate_svg(strace_results, keep_timestamps)
    view_results(svg_path)


if __name__ == "__main__":
    main()
