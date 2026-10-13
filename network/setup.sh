#!/usr/bin/env bash
# One-time setup on Ubuntu 22.04 / 24.04 (VM or WSL2). Run: bash setup.sh
set -e

sudo apt update
sudo DEBIAN_FRONTEND=noninteractive apt install -y \
    mininet iperf3 tcpdump tshark git iproute2 frr frr-pythontools \
    python3-networkx python3-matplotlib python3-pandas

# We start zebra/ospfd/ripd ourselves inside each Mininet node,
# so the system-wide FRR service must not run.
sudo systemctl disable --now frr 2>/dev/null || true

echo "--- checks ---"
ls /usr/lib/frr/zebra /usr/lib/frr/ospfd /usr/lib/frr/ripd
sudo ip netns add pshtest
sudo ip netns exec pshtest tc qdisc add dev lo root netem delay 10ms && echo "netem OK"
sudo ip netns del pshtest
echo "Setup OK. Next: sudo python3 psh_topo.py --proto ospf --check"
