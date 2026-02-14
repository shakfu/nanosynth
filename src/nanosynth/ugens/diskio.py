"""Disk I/O UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True, is_multichannel=True, has_done_flag=True)
class DiskIn(UGen):
    buffer_id = param()
    loop = param(0)


@ugen(ar=True, channel_count=0, fixed_channel_count=True)
class DiskOut(UGen):
    buffer_id = param()
    source = param(unexpanded=True)


@ugen(ar=True, is_multichannel=True, has_done_flag=True)
class VDiskIn(UGen):
    buffer_id = param()
    rate = param(1)
    loop = param(0.0)
    send_id = param(0)
