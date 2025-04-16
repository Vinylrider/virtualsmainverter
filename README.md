# virtualsmainverter
Summarize SMA and other JSON-compatible inverters into one virtual energy meter for SMA sunny island

The problem with SMA Sunny Portal is that you only can choose one SMA energy meter for Supply/Consume or Solar Supply. This usually is no problem because SMA Home manager can at least speak with all SMA solar inverters to get their values and feed it combined into sunny island. Now what if you have a Balkonkraftwerk (=one or more additional solar inverters from other manufacturers) ? Sunny Island will be blind about them and only your house consumption will decrease. 

There are different solutions. One is my other project : https://github.com/Vinylrider/virtualsmaenergymeter

But this version here reads out all SMA inverters by SMA speedwire protocol over LAN. Then reads out Hoymiles inverters by OpenDTU HTTP and gets their JSON file (which actually means you can bind in any inverter or counter, shelly, etc.. which offers JSON...).
The program also can include other SMA energy meters.
The software summarizes all supply values and counters and creates an virtual SMA energy meter just for PV supply. You can set this virtual emeter in sunny island as supply counter.

Example output :<br>
[INFO] SMA:192.168.1.62 P=2331.0W E=34042.126kWh | SMA:192.168.1.63 P=1940.0W E=34984.384kWh | SMA:192.168.1.64 P=2796.0W E=48024.895kWh | SMAMeter:1900123456 P=826.2W E=130.787kWh | SUM: P=7893.2W E=117182.192kWh
SUM values are sent as a virtual/emulated SMA energy meter. See example below :

<b>SMA-EM Serial:1900888888</b><br>
----sum----<br>
P: consume:0.0W 0.0kWh <b>supply:7893.2W 117182.192kWh</b><br>
S: consume:0.0VA 0.0kVAh supply:0.0VA 0.0VAh<br>
Q: cap 0.0var 0.0kvarh ind 0.0var 0.0kvarh<br>
cos phi:0.0Â°<br>
----L1----<br>
P: consume:0.0W 0.0kWh supply:0.0W 0.0kWh<br>
S: consume:0.0VA 0.0kVAh supply:0.0VA 0.0kVAh<br>
Q: cap 0.0var 0.0kvarh ind 0.0var 0.0kvarh<br>
U: 0.0V I:0.0A cos phi:0.0Â°<br>
----L2----<br>
P: consume:0.0W 0.0kWh supply:0.0W 0.0kWh<br>
S: consume:0.0VA 0.0kVAh supply:0.0VA 0.0kVAh<br>
Q: cap 0.0var 0.0kvarh ind 0.0var 0.0kvarh<br>
U: 0.0V I:0.0A cos phi:0.0Â°<br>
----L3----<br>
P: consume:0.0W 0.0kWh supply:0.0W 0.0kWh<br>
S: consume:0.0VA 0.0kVAh supply:0.0VA 0.0kVAh<br>
Q: cap 0.0var 0.0kvarh ind 0.0var 0.0kvarh<br>
U: 0.0V I:0.0A cos phi:0.0Â°<br>
Version: 1.2.4.R|010204<br>
<br>
As you see it is only supply values totals. This is enough for SMA Sunny island to detect the values when set as a "Bezugszähler" (=supply counter).<br>
<br>
Thanks to :<br>
https://github.com/datenschuft/SMA-EM : I use their "speedwiredecoder.py" for testing the emulator.<br>
https://github.com/Roeland54/SMA-Energy-Meter-emulator : I use their "emeter.py" for encoding, but had to fix an UDP protocol address so it is "emeter2.py" in my rep.<br>
https://github.com/eddso/ha_sma_speedwire/tree/main : I use their "sma_speedwire.py" to read out SMA inverters by speedwire (LAN) which is much more accurate and faster than Modbus !<br>
