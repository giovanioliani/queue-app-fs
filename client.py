import json
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet.protocol import ClientFactory
from twisted.internet.protocol import Protocol
from twisted.internet import reactor
from twisted.internet import stdio
from twisted.protocols.basic import LineReceiver
from sys import stdout

CONNECT_STRING = "connect\n\nevents text all\n\nfilter Event-Name"\
                 "CHANNEL_CREATE\n\n"

# class CommandReader(LineReceiver):
#     delimiter = '\n'
#     def connectionMade(self):
#         self.factory = CommandClientFactory()
#         self.connector = reactor.connectTCP("localhost", 5679, self.factory)

#     def lineReceived(self, line):
#         # Split command and argument
#         args = line.split(" ")
#         # Send command to server
#         self.connector.transport.write(json.dumps(dict(command=args[0],id=args[1])))

class QueueServerInterfaceProtocol(Protocol):
    def dataReceived(self, data):
        # Decodes result received from server and prints to stdout
        print json.loads(data).values()[0]

class CommandClientFactory(ClientFactory):
    def buildProtocol(self, addr):
        return QueueServerInterfaceProtocol()


class FreeSwitchInterfaceProtocol(Protocol):
    def __init__(self, factory):
        self.parent = factory
        self.queueConnector = reactor.connectTCP("localhost", 5679,
                                                 factory.commandFactory)
    def connectionMade(self):
        print "connected!"
        self.transport.write(CONNECT_STRING)

    def dataReceived(self, data):
        print data[12:data.find("\n\n")]
        #self.queueConnector.transport.write(json.dumps(dict(command="call",id="1")))

    def getIdentifier(self, event):
        """
        I return the unique call string identifier
        """
        # get start of string
        start = event.find("Unique-ID: ")

        # return id
        return event[start::event[start::].find("\n")]
    def do_call(self, data):
        #### put commands to send "originate bridge" here
        self.parent.newCall(getIdentifier(data))
        self.queueConnector.transport.write(json.dumps(dict("call",
                                            self.parent.callNumber-1)))

    def do_answer(self):
        #### commands to detect CHANNEL_ANSWER event and call server
        return
    def do_reject(self):
        #### commands to detect CHANNEL_HANGUP (call state ringing) event and
        #### call server
        return
    def do_hangup(self):
        #### commands to detect CHANNEL_HANGUP (call state active)event and
        #### call server
        return

class FreeSwitchInterfaceFactory(ClientFactory):
    def __init__(self):
        self.commandFactory = CommandClientFactory()
        # maps unique call identifiers into call numbers
        self.calls = {}
        self.callNumber = 1
    
    def newCall(self, uid):
        self.calls[uid] = self.callNumber
        self.callNumber = self.callNumber + 1

    def buildProtocol(self, addr):
        return FreeSwitchInterfaceProtocol(self)

point = TCP4ServerEndpoint(reactor, 5678)
point.listen(FreeSwitchInterfaceFactory())
reactor.run()