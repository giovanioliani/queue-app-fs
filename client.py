import json
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet.protocol import ClientFactory
from twisted.internet.protocol import Protocol
from twisted.internet import reactor

CONNECT_STRING = "connect\n\nevents text all\n\nfilter Event-Name "\
                 "CHANNEL_CREATE\n\nfilter Event-Name CHANNEL_ANSWER"\
                 "\n\nfilter Event-Name CHANNEL_HANGUP\n\n"

ORIGINATE_A = "api originate sofia/internal/operatorA@10.0.10.235:52271 "\
              "&bridge(user/1001)"

ORIGINATE_B = "api originate sofia/internal/operatorB@10.0.10.235:52271 "\
              "&bridge(user/1001)"

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

    def callMethod(self, event, eventName):
        print "debug-callMethod, eventName = " + eventName
        # if eventName == "CHANNEL_DATA":
        #     print "channel data answering"
        #     uuid = self.getField(event, "Unique-ID")
        #     self.sendMessageFS("api uuid_answer " + uuid)
        # event is CHANNEL_CREATE: register call identifier
        if eventName == "CHANNEL_CREATE":
            self.registerUID(event)

        # event is CHANNEL_ANSWER: call answer method
        elif eventName == "CHANNEL_ANSWER":
            self.do_answer(event)
        
        # event is CHANNEL_HANGUP: check if event is reject or hangup
        elif eventName == "CHANNEL_HANGUP":
            # get the call's call state before event
            callState = self.getField(event, "Channel-Call-State")
            
            # call state was RINGING: call reject method
            if  callState == "RINGING":
                self.do_reject(event)

            # call state was ACTIVE: call hangup method
            elif callState == "ACTIVE":
                self.do_hangup(event)


    def checkCallLeg(self, event):
        """
        I check whether ``event`` refers to the call leg with the operator
        number
        """
        # get detination number field
        dest = self.getField(event, "Caller-Destination-Number")
        
        # number is not one of the operator numbers: return False
        if dest != "operatorA" and dest != "operatorB":
            return False

        # number is one of the operator numbers: return True
        return True


    def connectionMade(self):
        # connect and start listening to relevant events
        self.sendMessageFS(CONNECT_STRING)

       # send call to queue server
        self.do_call()


    def dataReceived(self, data):
        print "debug-dataReceived"
        print data
        # data is not an event: return
        if self.isEvent(data) == False:
            return
        print "debug-isEvent"
        # event does not refer to an operator call leg: return
        if self.checkCallLeg(data) == False:
           return

        # call appropriate method to handle event
        reactor.callInThread(self.callMethod,data, self.getField(data, "Event-Name"))
    

    def do_call(self):
        print "debug-call"
        # operator A is busy: check if operator B is busy
        if self.parent.isABusy:

            # operator B is not busy: call operator B and set B as busy
            if not self.parent.isBBusy:
                self.sendMessageFS(ORIGINATE_B)
                self.parent.isBBusy = True
        
        # operator A is not busy: call operator A and set A as busy
        else:
            self.sendMessageFS(ORIGINATE_A)
            self.parent.isABusy = True

        # send call command to queue server
        self.sendMessageQueue(json.dumps(dict(command="call", 
                                         id=str(self.parent.callNumber))))


    def do_answer(self, event):
        print "answer event"
        # get call operator
        op = self.getField(event, "Caller-Destination-Number")
        
        # send answer command to queue server
        self.sendMessageQueue(json.dumps(dict(command="answer", 
                                         id=op[:len(op)-1])))


    def do_reject(self, event):
        print "reject event"
        # get call operator and trim the string
        op = self.getField(event, "Caller-Destination-Number")
        op = op[:len(op)-1]
        
        # operator is A: set A as not busy
        if op == "A":
            self.parent.isABusy = False
        # operator is B: set B as not busy
        else:
            self.parent.isBbusy = False

        # send reject ocmmand to queue server
        self.sendMessageQueue(json.dumps(dict(command="reject",id=op)))


    def do_hangup(self, event):
        print "hangup event"
        # get call identifier
        callID = self.getField(event, "Unique-ID")
        
        # get call operator
        op = self.getField(event, "Caller-Destination-Number")
        
        # if operator is A: set A as not busy
        if op[:len(op)-1] == "A":
            self.parent.isABusy = False
        # if operator is B: set B as not busy
        else:
            self.parent.isBbusy = False

        # send hangup command to queue server 
        self.sendMessageQueue(json.dumps(dict(command="hangup", 
                                         id=str(self.parent.idToNum[callID]))))


    def getField(self, event, field):
        """
        I return the event field value

        :type event: string
        :param event: event string to be searched

        :type field: string
        :param event: field name

        :rtype: string
        :returns: field value of the ``field`` field
        """
        # get position of field name
        start = event.find(field)
        
        # get position of field value
        start = event.find(":", start) + 2

        # return string from start of field value to end of line
        return event[start:event.find("\n", start)]


    def isEvent(self, event):
        # Event-Name field is in string: return true
        if event.find("Event-Name:") != -1:
            return True

        # Event-Name field is not in string: return false
        return False


    def registerUID(self, event):
        # event does not refer to an operator call leg: return
        if self.checkCallLeg(event) == False:
            return
        self.parent.newCall(self.getField(event, "Unique-ID"))


    def sendMessageFS(self, message):
        reactor.callInThread(self.transport.write, message)

    def sendMessageQueue(self, message):
        reactor.callInThread(self.queueConnector.transport.write, message)



class FreeSwitchInterfaceFactory(ClientFactory):
    def __init__(self):
        self.commandFactory = CommandClientFactory()
        # maps unique call identifiers into call numbers
        self.idToNum = {}
        
        # number of the next call to be sent to queue server
        self.callNumber = 1

        # operator A is busy
        self.isABusy = False

        # operator B is busy
        self.isBBusy = False
    

    def newCall(self, uid):
        # add mapping from call id to call number and increment call number
        self.idToNum[uid] = self.callNumber
        self.callNumber = self.callNumber + 1


    def buildProtocol(self, addr):
        return FreeSwitchInterfaceProtocol(self)


point = TCP4ServerEndpoint(reactor, 5678)
point.listen(FreeSwitchInterfaceFactory())
reactor.run()
#self.queueConnector.transport.write(json.dumps(dict(command="call", id="1")))