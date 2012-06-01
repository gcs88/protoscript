""" ad5452.py
    Functions used to monitor data passed to the ad5452 12-bit
    multiplying DAC via a SPI interface with the TotalPhase Beagle. 
    
    See beagle_py.py for more information about specific functions. """
    
from beagle_py import *
import array as ay # Data is sent and read as python's array type
import decimal as dc
import sys # For writing data to stdout
import time # For adding time delays for eeprom writes

#------------------------ Begin configure ------------------------------
port = 0 # Use detect() to set the port used by the Beagle analyzer.
megasamples = 50 # kHz -- The sample rate
timeout = 5000 # milliseconds --  The time the program will wait to
               # receive the specified number of packets.
latency = 200 # milliseconds -- The tradeoff between storing data in the
              # Beagle and storing data on the PC.
#------------------------- End configure -------------------------------


""" detect()
    Return port numbers for connected TotalPhase devices.  Use this
    function to see if the Beagle interface is working, and to set
    the port number above. """
def detect():
    print "Detecting Beagle adapters..."
    # Find all the attached devices
    (num, ports, unique_ids) = bg_find_devices_ext(16, 16)
    
    if num > 0:
        print "%d device(s) found:" % num
    
        # Print the information on each device
        for i in range(num):
            port      = ports[i]
            unique_id = unique_ids[i]
    
            # Determine if the device is in-use
            inuse = "(avail)"
            if (port & BG_PORT_NOT_FREE):
                inuse = "(in-use)"
                port  = port & ~BG_PORT_NOT_FREE
    
            # Display device port number, in-use status, and serial number
            print "    port = %d   %s  (%04d-%06d)" % \
                (port, inuse, unique_id / 1000000, unique_id % 1000000)
    else:
        print "No devices found."
        
""" gethandle()
    Return a handle to the Beagle. """
def gethandle():
    handle = bg_open(port)
    if (handle <= 0):
        print "Unable to open Beagle device on port %d" % port
        print "Error code = %d" % handle
        sys.exit()
    else:
        print 'Connected to Beagle device on port %d' % port
        return(handle)
        
""" initialize()
    Set up SPI communication specifically for the ad5452:
        Slave select active low
        Sample logic levels on falling clock edges
        MSB received first 
    Takes the handle returned by the gethandle() function. """
def initialize(handle):
    bg_disable(handle) # Disable the Beagle monitor
    
    # Set the idle timeout.
    # The Beagle read functions will return in the specified time
    # if there is no data available on the bus.
    bg_timeout(handle, timeout)
    print "Idle timeout set to %d ms" %  timeout
    
    # Configure the device for SPI
    bg_spi_configure(handle,
        BG_SPI_SS_ACTIVE_LOW,
        BG_SPI_SCK_SAMPLING_EDGE_FALLING,
        BG_SPI_BITORDER_MSB)
    bg_target_power(handle, BG_TARGET_POWER_OFF)
    
    # Set the sample rate in kilohertz (returns actual rate)
    actrate = bg_samplerate(handle, megasamples * 1000)
    print "Sample rate set to %d MHz" % int(actrate/1000)
    
    # Set the latency.
    # The latency parameter allows the programmer to balance the
    # tradeoff between host side buffering and the latency to
    # receive a packet when calling one of the Beagle read
    # functions.
    bg_latency(handle, latency)
    print "Latency set to %d ms" % latency
    
    # Enable the Beagle monitor
    bg_enable(handle, BG_PROTOCOL_SPI)
    

""" The main packet dump routine """
def spidump (handle, max_bytes, num_packets):

    # Get the size of timing information for each transaction of size
    # max_bytes
    timing_size = bg_bit_timing_size(BG_PROTOCOL_SPI, max_bytes)

    # Get the current sampling rate
    samplerate_khz = bg_samplerate(handle, 0)

    # Start the capture
    if (bg_enable(handle, BG_PROTOCOL_SPI) != BG_OK):
        print "error: could not enable SPI capture; exiting..."
        sys.exit(1)

    print "index,time(ns),SPI,status,mosi0/miso0 ... mosiN/misoN"
    sys.stdout.flush()

    i = 0

    # Allocate the arrays to be passed into the read function
    data_mosi  = array_u08(max_bytes)
    data_miso  = array_u08(max_bytes)
    bit_timing = array_u32(timing_size)

    # Capture and print information for each transaction
    while (i < num_packets or num_packets == 0):

        # Read transaction with bit timing data
        (count, status, time_sop, time_duration, time_dataoffset, data_mosi, \
         data_miso, bit_timing) = \
         bg_spi_read_bit_timing(handle, data_mosi, data_miso, bit_timing)

        # Translate timestamp to ns
        time_sop_ns = TIMESTAMP_TO_NS(time_sop, samplerate_khz);

        sys.stdout.write( "%d,%u,SPI,(" % (i, time_sop_ns))

        if (count < 0):
            print "error=%d,", count

        print_general_status(status)
        print_spi_status(status)
        sys.stdout.write( ")")

        # Check for errors
        i += 1
        if (count <= 0):
            print ""
            sys.stdout.flush()

            if (count < 0):
                break;

            # If zero data captured, continue
            continue;

        # Display the data
        for n in range(count):
            if (n != 0):         sys.stdout.write(", ")
            if ((n & 0xf) == 0): sys.stdout.write("\n    ")
            print "%02x/%02x" % (data_mosi[n], data_miso[n]),
        sys.stdout.write("\n")
        sys.stdout.flush()
    
    # Stop the capture
    bg_disable(handle)


#=======================================================================
# UTILITY FUNCTIONS
#=======================================================================
def TIMESTAMP_TO_NS(stamp, samplerate_khz):
    return (stamp * 1000L) / (samplerate_khz/1000L)

def print_general_status (status):
    """ General status codes """
    print "",
    if (status == BG_READ_OK) :
        print "OK",

    if (status & BG_READ_TIMEOUT):
        print "TIMEOUT",

    if (status & BG_READ_ERR_MIDDLE_OF_PACKET):
        print "MIDDLE",

    if (status & BG_READ_ERR_SHORT_BUFFER):
        print "SHORT BUFFER",

    if (status & BG_READ_ERR_PARTIAL_LAST_BYTE):
        print "PARTIAL_BYTE(bit %d)" % (status & 0xff),


def print_spi_status (status):
    """No specific SPI status codes"""
    pass
    
""" Sample usage """
def main():
    bg = gethandle()
    initialize(bg)
    # Read from SPI.  Data must appear on the bus within timeout.  The
    # ad5452 takes a two-byte write -- each packet consists of 2 bytes.
    spidump(bg, 2, 1)
    bg_close(bg) # Release the handle so other software can use the Beagle.

