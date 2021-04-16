import queue
import os
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand, UserError
from beets.ui.commands import import_cmd, import_func
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler


class WatchPlugin(BeetsPlugin):

    def __init__(self):
        super(WatchPlugin, self).__init__(name='watch')
        self.config.add({
            'paths': None,
            'recursive': True,
            'timeout': 1.0,
            'back_off': 30.0,
            'patterns': None,
            'ignore_patterns': None,
            'ignore_directories': False,
            'case_sensitive': True
        })

    def commands(self):
        watch_command = Subcommand('watch', help=u'watch directories and import new music on changes')
        watch_command.parser = import_cmd.parser
        watch_command.func = self.watch
        return [watch_command]

    def watch(self, lib, opts, args):
        if not args and not self.config['paths']:
            raise UserError(u'no path specified')

        watch_paths = args and set(map(os.path.abspath, args)) or set(
            map(os.path.abspath, self.config['paths'].as_str_seq()))
        timeout = self.config['timeout'].as_number()
        recursive = self.config['recursive']

        path_queue = queue.Queue()
        patterns = self.config['patterns'] and self.config['patterns'].as_str_seq() or None
        ignore_patterns = self.config['ignore_patterns'] and self.config['ignore_patterns'].as_str_seq() or None
        handler = WatchHandler(path_queue=path_queue,
                               patterns=patterns,
                               ignore_patterns=ignore_patterns,
                               ignore_directories=self.config['ignore_directories'],
                               case_sensitive=self.config['case_sensitive'])

        observer = Observer(timeout=timeout)
        for pathname in watch_paths:
            observer.schedule(handler, pathname, recursive)
        observer.start()

        import_paths = set()
        back_off = self.config['back_off'].as_number()

        self._log.info(u'watch_paths={0}', watch_paths)
        self._log.info(u'back_off={0}', back_off)
        self._log.info(u'patterns={0}', patterns)
        self._log.info(u'ignore_patterns={0}', ignore_patterns)
        self._log.info(u'ignore_directories={0}', self.config['ignore_directories'])
        self._log.info(u'case_sensitive={0}', self.config['case_sensitive'])
        self._log.info(u'opts={0}', opts)
        while True:
            try:
                import_path = path_queue.get(timeout=back_off)
                if import_path not in import_paths and import_path not in watch_paths and os.path.exists(import_path):
                    self._log.info(u'Adding: {0}', import_path)
                    import_paths.add(import_path)
                elif import_path in import_paths and not os.path.exists(import_path):
                    self._log.info(u'Removing: {0}', import_path)
                    import_paths.remove(import_path)
            except queue.Empty:
                if import_paths:
                    self._log.info(u'Importing: {0}', import_paths)
                    try:
                        import_func(lib, opts, list(import_paths))
                    except:
                        self._log.info(u'Import failed', exc_info=True)
                    finally:
                        self._log.info(u'Import done: {0}', import_paths)
                        import_paths.clear()


class WatchHandler(PatternMatchingEventHandler):

    def __init__(self, path_queue,
                 patterns=None,
                 ignore_patterns=None,
                 ignore_directories=False,
                 case_sensitive=True):
        super().__init__(patterns=patterns,
                         ignore_patterns=ignore_patterns,
                         ignore_directories=ignore_directories,
                         case_sensitive=case_sensitive)
        self.path_queue = path_queue

    def _process(self, event):
        path = event.src_path
        if not event.is_directory:
            path = os.path.dirname(path)
        self.path_queue.put(path)

    def on_created(self, event):
        self._process(event)

    def on_modified(self, event):
        self._process(event)
