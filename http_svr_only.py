#!/usr/local/bin/python3
'''
This script loads an HTTP server for /images
'''

import threading
import socketserver
import os, sys, time, socket
from nornir import InitNornir
from http.server import SimpleHTTPRequestHandler


# HTTP server for file transfer
class ThreadedHTTPServer(object):
    handler = SimpleHTTPRequestHandler
    def __init__(self, host, port):
        self.server = socketserver.TCPServer((host, port), self.handler)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True

    def start(self):
        self.server_thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


# Print formatting function
def c_print(printme):
    # Print centered text with newline before and after
    print(f"\n" + printme.center(80, ' ') + "\n")


def main():
  
    # initialize The Norn
    nr = InitNornir()

    # start the threaded HTTP server
    c_print("Starting HTTP server")

    # change directory to images
    os.chdir("/images")

    # set http server ip
    http_svr = nr.inventory.defaults.data['http_ip']

    c_print(f"http://{http_svr}:8000")
    # init http server
    server = ThreadedHTTPServer(http_svr, 8000)
    # start http server
    server.start()
    print('~'*80)

    quit = None
    while quit != True:
        c_print("*** Press (x) to quit ***")
        quit = input()
        if quit.lower() == 'x':
            quit = True

    # shut down the HTTP server
    server.stop()
    c_print("Stopping HTTP server")
    print('~'*80)


if __name__ == "__main__":
    main()
