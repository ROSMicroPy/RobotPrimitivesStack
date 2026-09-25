# Robie1: one workflow, three nodes

From the repository root, run:

```sh
python3 examples/robie1/main.py
```

The host-only example loads `arm.json`, `base.json`, and `controller.json` with
`NodeRuntime.load(...).boot()`. All service and transport choices are in those
manifests. The controller manifest autostarts `reach`; the runner prints its result
and each node's execution status. No robot hardware or ROS installation is used.

The controller first moves the base on a simulated ROS link, then moves the arm
on a simulated mesh link. It bridges both networks, so the arm can also address
the base through the controller. The mesh link intentionally duplicates packets;
operations still execute once. All nodes share entity `Robie1` and have distinct
node identities. One coordinator advances each workflow; peers execute actions
and observe revisioned state signals.

For a deployment, replace `simulation:MemoryTransport` with
`rpstack.espnow:EspNowTransport` and/or `rpstack.ros_signals:RosTransport`, and
replace the simulated joint component with the actual service contract. Retain
matching entity, peer and exposure configuration. The sample `simulation` module
is for host testing and is not a hardware driver.

See [signal configuration and execution semantics](../../RPStack/runtime/signals/README.md),
including cancellation leases, reset generations and delivery limits.
