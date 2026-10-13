# network/ (Member 1: Network and Baselines)

Mininet + FRRouting test network for PSH-RP.

```
h1 -- r1 ---- r2 ---- r6 -- h2      primary    (shortest, preferred by OSPF and RIP)
       \      |  \    /
        \     |   r5 /               r2-r5 = noisy link (S4 false-alarm test)
         r3 -- r4 ----               alternate  (r1-r3-r4-r6)
```

## Setup (once)

```bash
cd network
bash setup.sh
```

## Run

```bash
sudo python3 psh_topo.py --proto ospf --check          # Week 1 gate: converge, print, exit
sudo python3 psh_topo.py --proto ospf                  # OSPF + Mininet CLI
sudo python3 psh_topo.py --proto ospf --timers tuned   # hello 1 s / dead 3 s
sudo python3 psh_topo.py --proto rip                   # RIP
sudo python3 psh_topo.py --proto ospf --noisy          # r2-r5 jittery
sudo mn -c                                             # clean up after a crash
```

## In the Mininet CLI

```
h1 ping h2
r1 vtysh --vty_socket /tmp/pshrp/r1 -c "show ip route"
r1 vtysh --vty_socket /tmp/pshrp/r1 -c "show ip ospf neighbor"
py net.netem.degrade(net,'r2','r6',delay_ms=80,jitter_ms=10,loss_pct=3)
py net.netem.cut(net,'r2','r6')
py net.netem.ramp(net,'r2','r6',duration=30)
```

## Contract with the other modules (do not change without telling the team)

| Item | Value |
|---|---|
| Nodes | `r1`..`r6`, `h1`, `h2` |
| Interface name | `<self>-<peer>`, e.g. `r2-r6` is r2's port towards r6 |
| Link subnets | `10.0.<i>.0/30`, i = position in `LINKS` (first node .1, second .2) |
| Host LANs | `192.168.1.0/24` (h1 .10) and `192.168.2.0/24` (h2 .10) |
| Logs | FRR logs in `/tmp/pshrp/<router>/` |
| Timestamps | `time.time()` epoch seconds (ramp start, cut), so they match probe and swap logs |

## Troubleshooting

- `h1 cannot reach h2`: check `/tmp/pshrp/r1/ospfd.log` and `zebra.log`. Make sure the system `frr` service is disabled.
- `vtysh` cannot connect: confirm the daemons run with `ps aux | grep frr`.
- Leftover state: `sudo mn -c` and `sudo pkill -f /usr/lib/frr/`.
