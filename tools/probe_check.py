from mininet.net import Mininet
from mininet.node import OVSBridge
from mininet.topo import SingleSwitchTopo
from mininet.log import setLogLevel
from engine.telemetry import probe

setLogLevel("warning")
net = Mininet(SingleSwitchTopo(2), switch=OVSBridge, controller=None)
net.start()
h1, h2 = net.get("h1", "h2")
ip = h2.IP()
print("clean", probe(h1, "h1-eth0", ip))
h1.cmd("tc qdisc add dev h1-eth0 root netem delay 50ms loss 20%")
print("degraded", probe(h1, "h1-eth0", ip))
net.stop()
