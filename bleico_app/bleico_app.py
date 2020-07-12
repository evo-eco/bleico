# @Author: carlosgilgonzalez
# @Date:   2020-07-12T15:41:44+01:00
# @Last modified by:   carlosgilgonzalez
# @Last modified time: 2020-07-12T17:12:56+01:00
"""
Copyright (c) 2020 Carlos G. Gonzalez and others (see the AUTHORS file).
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""


import logging
import sys
from bleico.socket_client_server import socket_server
from bleak.backends.corebluetooth.utils import cb_uuid_to_str
from bleak.utils import get_char_value, pformat_char_value
import os
from bleico.ble_device import BLE_DEVICE  # get own ble_device
from bleico.chars import ble_char_dict, ble_char_dict_rev  # get own chars
from bleico.devtools import store_dev, load_dev  # get own devtools
from datetime import datetime
import time
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction, QSplashScreen
from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot, Qt
import traceback
import asyncio

frozen = 'not'
if getattr(sys, 'frozen', False):
        # we are running in a bundle
        frozen = 'ever so'
        bundle_dir = sys._MEIPASS
else:
        # we are running in a normal Python environment
        bundle_dir = os.path.dirname(os.path.abspath(__file__))


# TODO: DEVICE STATE, LAST UPDATE
# helparg = '''Mode:
# - config
# - run
# '''
#
# usag = """%(prog)s [Mode] [options]
# """
# # UPY MODE KEYWORDS AND COMMANDS
# keywords_mode = ['config', 'run']
# log_levs = ['debug', 'info', 'warning', 'error', 'critical']
# parser = argparse.ArgumentParser(prog='bleico',
#                                  description='Bluetooth Low Energy System Tray Icon',
#                                  formatter_class=argparse.RawTextHelpFormatter,
#                                  usage=usag)
# parser.version = '0.0.1'
# parser.add_argument(
#     "m", metavar='Mode', help=helparg)
# parser.add_argument('-v', action='version')
# parser.add_argument('-t', help='device target uuid')
# parser.add_argument('-debug', help='debug info log', action='store_true')
# parser.add_argument('-dflev',
#                     help='debug file mode level, options [debug, info, warning, error, critical]',
#                     default='error').completer = ChoicesCompleter(log_levs)
# parser.add_argument('-dslev',
#                     help='debug sys out mode level, options [debug, info, warning, error, critical]',
#                     default='info').completer = ChoicesCompleter(log_levs)
# args = parser.parse_args()

SRC_PATH = bundle_dir


# THREAD WORKERS
class WorkerSignals(QObject):
    '''
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data

    error
        `tuple` (exctype, value, traceback.format_exc() )

    result
        `object` data returned from processing, anything

    progress
        `int` indicating % progress

    '''
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    progress = pyqtSignal(object)


class Worker(QRunnable):
    '''
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    '''

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.kwargs['progress_callback'] = self.signals.progress

    @pyqtSlot()
    def run(self):
        '''
        Initialise the runner function with passed args, kwargs.
        '''

        # Retrieve args/kwargs here; and fire processing using them
        try:
            self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        # Return the result of the processing
        finally:
            self.signals.finished.emit()


class SystemTrayIcon(QSystemTrayIcon):
    def __init__(self, icon, parent=None, device_uuid=None,
                 logger=None, debug=False, max_tries=1):
        QSystemTrayIcon.__init__(self, icon, parent)
        self.debug = debug
        self.log = logger
        self._ntries = 0
        # SPLASH SCREEN
        # Splash Screen
        self.splash_pix = QPixmap(SRC_PATH+"/bleico.png", 'PNG')
        self.scaled_splash = self.splash_pix.scaled(512, 512, Qt.KeepAspectRatio, transformMode = Qt.SmoothTransformation)
        self.splash = QSplashScreen(self.scaled_splash, Qt.WindowStaysOnTopHint)
        self.splash.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.splash.setEnabled(False)
        self.splash.show()
        self.splash.showMessage("Scanning for device...",
                                Qt.AlignHCenter | Qt.AlignBottom, Qt.white)
        # Upydevice
        self.esp32_device = BLE_DEVICE(device_uuid, init=True)
        while not self.esp32_device.connected:
            if self._ntries <= max_tries:
                self.esp32_device = BLE_DEVICE(device_uuid, init=True)
                time.sleep(2)
                self._ntries += 1
            else:
                self.log.error("Device {} not found".format(device_uuid))
                self.splash.clearMessage()
                self.splash.showMessage("Device {} not found".format(device_uuid),
                                        Qt.AlignHCenter | Qt.AlignBottom, Qt.white)
                time.sleep(2)
                self.splash.clearMessage()
                self.splash.close()
                sys.exit()
        self.splash.clearMessage()
        # Create the menu
        if "{}.png".format(self.esp32_device.appearance_tag) not in os.listdir(SRC_PATH):
            self.app_icon = QIcon(SRC_PATH+"/UNKNOWN.png")
        else:
            self.app_icon = QIcon(SRC_PATH+"/{}.png".format(self.esp32_device.appearance_tag))
        self.app_icon.setIsMask(True)
        self.setIcon(self.app_icon)
        self.splash.showMessage("Device {} found".format(self.esp32_device.name),
                                Qt.AlignHCenter | Qt.AlignBottom, Qt.white)
        self.menu = QMenu(parent)
        # DEVICE INFO
        self.device_label = QAction("Device: ?")
        self.menu.addAction(self.device_label)
        self.uuid_menu = self.menu.addMenu("UUID")
        self.uuid_label = QAction("X")
        self.uuid_label.setEnabled(False)
        self.uuid_menu.addAction(self.uuid_label)
        self.separator = QAction()
        self.separator.setSeparator(True)
        self.menu.addAction(self.separator)
        # SERVICES
        # AVOID READ CHARS
        self.special_formats = ['utf8', 'utf8s', 'bytemask']
        self.avoid_chars = ['Appearance', 'Manufacturer Name String',
                            'Battery Power State', 'Model Number String',
                            'Firmware Revision String']

        self.serv_menu = self.menu.addMenu("Services")
        # self.serv_label.setEnabled(False)
        # self.serv_menu.addAction(self.serv_label)
        # main_serv = list(self.esp32_device.services_rsum.keys())[0]
        # main_serv_char = self.esp32_device.services_rsum[main_serv][0]
        # self.main_service = QAction("{} : {}".format(main_serv, main_serv_char))
        # self.serv_menu.addAction(self.main_service)
        if self.debug:
            self.log.info("Device {} found".format(self.esp32_device.name))
            self.log.info("Services:")
        for serv in self.esp32_device.services_rsum.keys():
            self.serv_action = self.serv_menu.addMenu("{}".format(serv))
            if self.debug:
                self.log.info(" (S) {}".format(serv))
            for char in self.esp32_device.services_rsum[serv]:
                if self.debug:
                    self.log.info(" (C)  - {}".format(char))
                self.serv_action.addAction(char)
            # self.serv_menu.addAction(self.main_service)
        self.servs_separator = QAction()
        self.servs_separator.setSeparator(True)
        self.menu.addAction(self.servs_separator)
        self.serv_actions_dict = {serv: QAction(serv) for serv in self.esp32_device.services_rsum.keys()}
        self.serv_separator_dict = {}
        self.char_actions_dict = {}
        self.notify_char_menu_dict = {}
        self.notify_char_actions_dict = {}
        self.battery_power_state_actions_dict = {}
        for key, serv in self.serv_actions_dict.items():
            if key == 'Device Information':
                self.devinfo_menu = self.menu.addMenu(key)
                for char in self.esp32_device.services_rsum[key]:
                    self.char_actions_dict[char] = self.devinfo_menu.addAction("{}: {}".format(char.replace('String', ''), self.esp32_device.device_info[char]))
                    self.char_actions_dict[char].setEnabled(False)
                self.menu.addSeparator()
            else:
                serv.setEnabled(False)
                self.menu.addAction(serv)
                for char in self.esp32_device.services_rsum[key]:
                    if char in self.avoid_chars:
                        if char == 'Battery Power State':
                            self.char_actions_dict[char] = self.menu.addMenu(char)
                            for state, value in self.esp32_device.batt_power_state.items():
                                self.battery_power_state_actions_dict[state]=self.char_actions_dict[char].addAction("{}: {}".format(state,value))  # store actions in dict to update
                        else:
                            self.char_actions_dict[char] = self.menu.addMenu(char)
                            self.char_actions_dict[char].addAction(self.esp32_device.device_info[char])
                    else:
                        # HERE DIVIDE CHARS INTO SINGLE/FEATURES/MULTIPLE, READ CHAR --> CLASSIFY [A,B,C...]
                        self.char_actions_dict[char] = QAction("{}: ? ua".format(char))
                        self.menu.addAction(self.char_actions_dict[char])
                self.serv_separator_dict[key] = QAction()
                self.serv_separator_dict[key].setSeparator(True)
                self.menu.addAction(self.serv_separator_dict[key])
        self.separator_etc = QAction()
        self.separator_etc.setSeparator(True)
        self.menu.addAction(self.separator_etc)
        self.notifiable_label = QAction("Notify")
        self.notifiable_label.setEnabled(False)
        self.menu.addAction(self.notifiable_label)
        for char in self.esp32_device.notifiables.keys():
            self.notify_char_menu_dict[char] = self.menu.addMenu(char)
            self.notify_char_actions_dict[char] = self.notify_char_menu_dict[char].addAction('Notify')
            self.notify_char_actions_dict[char].triggered.connect(self.check_which_triggered)
            # here trigger action --> set flag notify True, start Thread, callback notify ...

        # TIME LAST UPDATE
        self.menu.addSeparator()
        self.last_update_action = QAction()
        self.last_update_action.setEnabled(False)
        self.menu.addAction(self.last_update_action)
        self.separator_exit = QAction()
        self.separator_exit.setSeparator(True)
        self.menu.addAction(self.separator_exit)
        self.exitAction = self.menu.addAction("Exit")
        self.exitAction.triggered.connect(self.exit_app)
        self.setContextMenu(self.menu)
        self.device_label.setText('Device: {}'.format(
            self.esp32_device.name))

        self.uuid_label.setText('{}'.format(self.esp32_device.UUID))
        # Workers
        self.threadpool = QThreadPool()
        self.quit_thread = False
        self.main_server = None
        if self.debug:
            self.log.info("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())

        if self.debug:
            self.log.info('Device: {}, UUID: {}'.format(self.esp32_device.name,
                                                        self.esp32_device.UUID))
        self.splash.clearMessage()
        self.splash.close()

        # NOTIFIABLE
        self.char_to_notify = None
        self.chars_to_notify = []
        self.notify_is_on = False
        # self.notify_loop = None
        self.notify_loop = asyncio.new_event_loop()

        # AVOID READ
        self.avoid_chars = ['Appearance', 'Manufacturer Name String',
                            'Battery Power State', 'Model Number String',
                            'Firmware Revision String']
        # ON EXIT
        self.ready_to_exit = False

    def check_which_triggered(self, checked):
        action = self.sender()
        for char in self.notify_char_actions_dict.keys():
            if action == self.notify_char_actions_dict[char]:
                if char not in self.chars_to_notify:
                    self.log.info("Char: {} Notification Enabled".format(char))
                    self.char_to_notify = char
                    # for char in self.esp32_device.notifiables.keys():
                    self.chars_to_notify.append(char)
                    action.setText('Stop Notification')
                    # action.triggered.connect(self.check_which_triggered) # stop notify Thread
                    if self.main_server:
                        self.main_server.send_message("start:{}".format(char))
                    else:
                        self.start_notify_char()
                        self.notify_is_on = True
                else:
                    self.log.info("Char: {} Notification Disabled".format(char))
                    self.chars_to_notify.remove(char)
                    self.main_server.send_message("stop:{}".format(char))
                    # self.stop_notify_thread()
                    action.setText('Notify')
                    # self.notify_is_on = False
                    # self.char_to_notify = None
                    # action.triggered.connect(self.check_which_triggered)
            # Here

    # def set_dark_mode_ICON(self):
    #     self.setIcon(QIcon(bleico.__path__[0]+"/{}_dark.png".format(self.esp32_device.appearance)))
    #
    # def set_day_mode_ICON(self):
    #     self.setIcon(QIcon(bleico.__path__[0]+"/{}.png".format(self.esp32_device.appearance)))
    #
    # def autoset_icon(self, n):  # worker callback
    #     if n == 1:
    #         self.set_dark_mode_ICON()
    #     else:
    #         self.set_day_mode_ICON()
    #
    # def update_icon(self, progress_callback):  # in thread
    #     while True:
    #         if self.quit_thread:
    #             break
    #         else:
    #             self.theme = darkdetect.theme()
    #             if self.theme == 'Dark':
    #                 progress_callback.emit(1)
    #             else:
    #                 progress_callback.emit(0)
    #         time.sleep(1)
    #
    # def start_update_icon(self):
    #     # Pass the function to execute
    #     worker = Worker(self.update_icon)  # Any other args, kwargs are passed to the run function
    #     # worker.signals.result.connect(self.print_output)
    #     # worker.signals.finished.connect(self.thread_complete)
    #     worker.signals.progress.connect(self.autoset_icon)  # connect callback
    #
    #     # Execute
    #     self.threadpool.start(worker)

    def refresh_menu(self, response):

        # data = self.esp32_device.read_char(key='Environmental Sensing', data_fmt="f")[0]
        data = response
        if data == 'finished':
            self.log.info("MENU CALLBACK: THREAD FINISH RECEIVED")
            self.ready_to_exit = True
        else:
            try:
                for char in data.keys():
                    # HANDLE SINGLE VALUES
                    char_text = self.esp32_device.pformat_char_value(data[char],
                                                                     char=char,
                                                                     rtn=True,
                                                                     prnt=False,
                                                                     one_line=True,
                                                                     only_val=True)

                    self.char_actions_dict[char].setText(char_text)
                    if self.debug:
                        for serv in self.esp32_device.services_rsum.keys():
                            if char in self.esp32_device.services_rsum[serv]:
                                self.log.info("[{}] {}".format(serv, char_text))
                    # TODO: HANDLE BITFLAGS
                    # TODO: HANDLE MULTIPLE VALUES
                self.last_update_action.setText("Last Update: {}".format(datetime.strftime(datetime.now(), "%H:%M:%S")))
            except Exception as e:
                if self.debug:
                    self.log.error(e)

    def update_menu(self, progress_callback):  # define the notify callback inside that takes progress_callback as variable
        while not self.quit_thread:
            if self.quit_thread:
                break
            else:
                try:
                    data = {}
                    for char in self.esp32_device.readables.keys():
                        if char not in self.avoid_chars and char not in self.chars_to_notify:
                            # if self.esp32_device.chars_xml[char].fmt is None:
                            #     self.esp32_device.chars_xml[char].fmt = 'B'
                            if self.quit_thread:
                                break
                            else:
                                data[char] = (self.esp32_device.get_char_value(char))
                    progress_callback.emit(data)
                except Exception as e:
                    progress_callback.emit(False)
            time.sleep(1)
        progress_callback.emit("finished")
        time.sleep(1)
        self.ready_to_exit = True
        self.log.info("THREAD MENU: FINISHED")
        # progress_callback.emit("finished")

    def start_update_menu(self):
        # Pass the function to execute
        worker_menu = Worker(self.update_menu) # Any other args, kwargs are passed to the run function
        # worker.signals.result.connect(self.print_output)
        # worker.signals.finished.connect(self.thread_complete)
        # worker.signals.progress.connect(self.progress_fn)
        worker_menu.signals.progress.connect(self.refresh_menu)

        # Execute
        self.threadpool.start(worker_menu)

    def receive_notification(self, response):

        data = response
        try:
            for char in data.keys():
                if char != 'Battery Power State':
                    # if self.esp32_device.chars_xml[char].dec_exp is not None:
                    #     data[char] = data[char]*10**(self.esp32_device.chars_xml[char].dec_exp)
                    data_value = get_char_value(data[char], self.esp32_device.chars_xml[char])
                    data_value_string = pformat_char_value(data_value,
                                                           rtn=True,
                                                           prnt=False,
                                                           one_line=True,
                                                           only_val=True)
                    self.char_actions_dict[char].setText(
                        "{}: {}".format(char, data_value_string))
                    for serv in self.esp32_device.services_rsum.keys():
                        if char in self.esp32_device.services_rsum[serv]:
                            nservice = serv
                    self.notify("{}@{}:".format(self.esp32_device.name, nservice), "{} Is now: {}".format(
                        char, data_value_string))

                    if self.debug:
                        for serv in self.esp32_device.services_rsum.keys():
                            if char in self.esp32_device.services_rsum[serv]:
                                self.log.info("Notification: {} [{}] : {}".format(serv, char, data_value_string))
                else:
                    data_value = get_char_value(data[char], self.esp32_device.chars_xml[char])
                    self.esp32_device.batt_power_state = self.esp32_device.map_powstate(data_value['State']['Value'])
                    # self.esp32_device.unpack_batt_power_state(data[char])
                    for state, value in self.esp32_device.batt_power_state.items():
                        self.battery_power_state_actions_dict[state].setText("{}: {}".format(state, value))
                    for serv in self.esp32_device.services_rsum.keys():
                        if char in self.esp32_device.services_rsum[serv]:
                            nservice = serv
                    self.notify("{}@{}:".format(self.esp32_device.name, nservice), "{} Is now: {} {}".format(char, self.esp32_device.batt_power_state['Charging State'],
                                                                                                          self.esp32_device.batt_power_state['Level']))

                    if self.debug:
                        for serv in self.esp32_device.services_rsum.keys():
                            if char in self.esp32_device.services_rsum[serv]:
                                self.log.info("Notification: {} [{}] : {} {}".format(serv,
                                                                                     char, self.esp32_device.batt_power_state['Charging State'],
                                                                                     self.esp32_device.batt_power_state['Level']))
        except Exception as e:
            if self.debug:
                self.log.error(e)

    def subscribe_notify(self, progress_callback):  # run in thread

        def readnotify_callback(sender, data, callb=progress_callback):

            char = ble_char_dict[cb_uuid_to_str(sender)]
            try:
                data_dict = {char: data}
                callb.emit(data_dict)
            except Exception as e:
                self.log.error(e)

        async def as_char_notify(notify_callback=readnotify_callback):
            aio_client_r, aio_client_w = await asyncio.open_connection('localhost', self.port)
            aio_client_w.write('started'.encode())
            for char in self.chars_to_notify:
                await self.esp32_device.ble_client.start_notify(ble_char_dict_rev[char], notify_callback)
            await asyncio.sleep(1)
            while True:
                data = await aio_client_r.read(1024)
                message = data.decode()
                self.log.info('NOTIFY_THREAD: {}'.format(message))
                if message == 'exit':
                    # await self.esp32_device.ble_client.stop_notify(ble_char_dict_rev[self.char_to_notify])
                    aio_client_w.write('ok'.encode())
                    self.log.info('NOTIFY_THREAD: {}'.format("Stopping notification now..."))
                    for char in self.chars_to_notify:
                        await self.esp32_device.ble_client.stop_notify(ble_char_dict_rev[char])
                    aio_client_w.close()
                    self.log.info('NOTIFY_THREAD: {}'.format("Done!"))
                    self.char_to_notify = None
                    break
                else:
                    action, char = message.split(':')
                    if action == 'start':
                        await self.esp32_device.ble_client.start_notify(ble_char_dict_rev[char], notify_callback)
                    if action == 'stop':
                        await self.esp32_device.ble_client.stop_notify(ble_char_dict_rev[char])
                    await asyncio.sleep(1)

        # async def unsubscribe_char():
        #     self.log.info('NOTIFY_THREAD: {}'.format("Stopping notification now..."))
        #     await self.esp32_device.ble_client.stop_notify(ble_char_dict_rev[self.char_to_notify])
        #     self.log.info('NOTIFY_THREAD: {}'.format("Done!"))

        # GET NEW EVENT LOOP AND RUN
        try:
            asyncio.set_event_loop(self.notify_loop)
            # n_loop.set_debug(True)
            # asyncio.run_coroutine_threadsafe(as_char_notify(), self.esp32_device.loop)
            self.notify_loop.run_until_complete(as_char_notify())
            # self.notify_loop.run_until_complete(unsubscribe_char())
            # self.notify_loop.stop()
            # self.notify_loop.close()
        except Exception as e:
            self.log.error('NOTIFY_THREAD: {}'.format(e))
        # progress_callback.emit(False)
        self.log.info('NOTIFY_THREAD: {}'.format("THREAD FINISHED"))

    def start_notify_char(self):
        # Pass the function to execute
        worker_notify = Worker(self.subscribe_notify) # Any other args, kwargs are passed to the run function
        # worker.signals.result.connect(self.print_output)
        # worker.signals.finished.connect(self.thread_complete)
        # worker.signals.progress.connect(self.progress_fn)
        worker_notify.signals.progress.connect(self.receive_notification)

        # Execute
        # self.threadpool.start(worker_notify)
        self.main_server = socket_server(8845)
        self.port = self.main_server.get_free_port() # start stop multiple chars to notify
        self.threadpool.start(worker_notify)
        self.main_server.start_SOC()
        self.log.info("NOTIFY_THREAD: {}".format(self.main_server.recv_message()))

    def notify(self, typemessage, message):
        """Generate a desktop notification"""
        self.showMessage(typemessage,
                         message,
                         QSystemTrayIcon.Warning,
                         60*60000)

    def shutdown(self, loop):
        # self.log.info("Shutdown...")

        try:
            loop.stop()
        except Exception as e:
            # print(e)
            pass
        # Find all running tasks:
        try:
            pending = asyncio.all_tasks(loop)

        # Run loop until tasks done:
            loop.run_until_complete(asyncio.gather(*pending))
        except Exception as e:
            # print(e)
            pass

        self.log.info("ASYNCIO EVENT LOOP: SHUTDOWN COMPLETE")
        self.ready_to_exit = True
        # try:
        #     if self.esp32_device.connected:
        #         self.esp32_device.disconnect()
        #     self.log.info("Here...")
        # except Exception as e:
        #     # print(e)
        #     pass

    def stop_notify_thread(self):

        # REINITIATE THREADS

        try:

            self.main_server.send_message('exit')
            self.main_server.recv_message()
            self.main_server.serv_soc.close()
        except Exception as e:
            self.log.error(e)

    def exit_app(self):
        if self.debug:
            self.log.info('Closing now...')
            self.log.info('Done!')
            self.log.info('Shutdown pending tasks...')
        try:
            self.quit_thread = True
            self.main_server.send_message('exit')
            self.main_server.recv_message()
            self.main_server.serv_soc.close()
        except Exception as e:
            self.quit_thread = True
            self.log.error(e)
        loop_is_running = self.esp32_device.loop.is_running()
        self.log.info("LOOP IS RUNNING : {}".format(loop_is_running))
        if loop_is_running:
            self.shutdown(self.esp32_device.loop)
        # loop_is_running = self.notify_loop.is_running()
        # self.log.info("NOTIFY LOOP IS RUNNING : {}".format(loop_is_running))
        # if loop_is_running:
        #     self.shutdown(self.notify_loop)
        # self.esp32_device.loop.stop()
        # Run loop until tasks done

        time.sleep(2)

        try:
            while not self.ready_to_exit:
                self.log.info("Waiting for menu thread")
                time.sleep(1)
            self.log.info("Disconnecting Device...")
            if self.esp32_device.connected:
                self.esp32_device.disconnect()
        except Exception as e:
            pass
        self.log.info("SHUTDOWN COMPLETE")
        sys.exit()


#############################################


# if '.upydevices' not in os.listdir("{}".format(os.environ['HOME'])):
#     os.mkdir("{}/.upydevices".format(os.environ['HOME']))
# # Config device option
# if args.m == 'config':
#     if args.t is None:
#         print('Target uuid required, see -t')
#         sys.exit()
#     store_dev('bleico_', uuid=args.t)
#
#     print('bleico device settings saved in upydevices directory!')
#     sys.exit()

if True:

    banner = """
$$$$$$$\  $$\       $$$$$$$$\ $$$$$$\  $$$$$$\   $$$$$$\\
$$  __$$\ $$ |      $$  _____|\_$$  _|$$  __$$\ $$  __$$\\
$$ |  $$ |$$ |      $$ |        $$ |  $$ /  \__|$$ /  $$ |
$$$$$$$\ |$$ |      $$$$$\      $$ |  $$ |      $$ |  $$ |
$$  __$$\ $$ |      $$  __|     $$ |  $$ |      $$ |  $$ |
$$ |  $$ |$$ |      $$ |        $$ |  $$ |  $$\ $$ |  $$ |
$$$$$$$  |$$$$$$$$\ $$$$$$$$\ $$$$$$\ \$$$$$$  | $$$$$$  |
\_______/ \________|\________|\______| \______/  \______/
    """
    print('*'*60)
    print(banner)
    print('*'*60)

    config_file_name = 'bleico_.config'
    config_file_path = "{}/.blewiz".format(os.environ['HOME'])
    device_is_configurated = config_file_name in os.listdir(config_file_path)
    # Logging Setup

    # filelog_path = "{}/.upydevices_logs/weatpyfluxd_logs/".format(
    #     os.environ['HOME'])
    log_levels = {'debug': logging.DEBUG, 'info': logging.INFO,
                  'warning': logging.WARNING, 'error': logging.ERROR,
                  'critical': logging.CRITICAL}
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_levels['info'])
    logging.basicConfig(
        level=log_levels['debug'],
        format="%(asctime)s [%(name)s] [%(levelname)s] %(message)s",
        # format="%(asctime)s [%(name)s] [%(process)d] [%(threadName)s] [%(levelname)s]  %(message)s",
        handlers=[handler])
    log = logging.getLogger('bleico')  # setup one logger per device
    log.info('Running bleico {}'.format('0.0.1'))


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)

    # Open upydevice configuration
    if device_is_configurated:
        upy_conf = load_dev('bleico_', dir=config_file_path)
        if upy_conf is None:
            log.error("CONFIGURATION FILE NOT FOUND")
            sys.exit()
    # Create the icon

    icon = QIcon(SRC_PATH+"/UNKNOWN.png")
    icon.setIsMask(True)
    trayIcon = SystemTrayIcon(icon, device_uuid=upy_conf['uuid'],
                              logger=log, debug=True)
    # Menu refresher
    # trayIcon.start_update_icon()
    trayIcon.start_update_menu()

    trayIcon.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
