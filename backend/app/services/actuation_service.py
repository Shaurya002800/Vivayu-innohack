"""Approved-decision execution remains deferred until later milestones.

Milestone 10 command transport, ACK tracking and STOP_ALL safety are owned by
``serial_bridge.py``; this module must not wire M4-M6 previews into actuation.
"""
