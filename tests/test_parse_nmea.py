import pytest
import parse_nmea
from parse_nmea import NMEAParsingError, UnknownNMEASentence

def test_checksum():
    assert parse_nmea.checksum("GPGLL,4916.45,N,12311.12,W,225444,A") == 0x31
    assert parse_nmea.checksum("GPRMC,225446,A,4916.45,N,12311.12,W,000.5,054.7,191125,020.3,E") == 0x62

def test_parse_invalid():
    with pytest.raises(NMEAParsingError):
        parse_nmea.parse("INVALID")
    
    with pytest.raises(NMEAParsingError):
        # Bad checksum
        parse_nmea.parse("$GPGLL,4916.45,N,12311.12,W,225444,A*00")

def test_parse_unknown():
    # Correct checksum for GPXYZ,1,2,3 is 0x50
    with pytest.raises(UnknownNMEASentence) as excinfo:
        parse_nmea.parse("$GPXYZ,1,2,3*50")
    assert excinfo.value.sentence_type == "XYZ"

def test_hdt():
    # $HEHDT,234.2,T*28
    af, data = parse_nmea.parse("$HEHDT,234.2,T*28")
    assert af == "HEHDT"
    assert data["hdg_true"] == 234.2
    assert data["sentence_type"] == "HDT"
    
    # Test without checksum (should still work)
    af, data = parse_nmea.parse("$HEHDT,234.2,T")
    assert data["hdg_true"] == 234.2

    with pytest.raises(NMEAParsingError):
        parse_nmea.parse("$HEHDT,234.2,M*12")

def test_dpt():
    # $IIDPT,005.1,0.0,100.0*47
    af, data = parse_nmea.parse("$IIDPT,005.1,0.0,100.0*47")
    assert af == "IIDPT"
    assert data["depth_below_transducer_meters"] == 5.1
    assert data["transducer_depth_meters"] == 0.0
    assert data["water_depth_meters"] == 5.1

def test_mda():
    # $IIMDA,30.0,I,1.018,B,25.0,C,,,75.0,,15.0,C,090.0,T,085.0,M,10.0,N,05.1,M*7C
    af, data = parse_nmea.parse("$IIMDA,30.0,I,1.018,B,25.0,C,,,75.0,,15.0,C,090.0,T,085.0,M,10.0,N,05.1,M*7C")
    assert af == "IIMDA"
    assert data["pressure_inches"] == 30.0
    assert data["pressure_bars"] == 1.018
    assert data["pressure_millibars"] == 1018.0
    assert data["temperature_air_celsius"] == 25.0
    assert data["humidity_relative"] == 75.0
    assert data["twd_true"] == 90.0
    assert data["tws_knots"] == 10.0

def test_vtg():
    # $GPVTG,054.7,T,034.4,M,005.5,N,010.2,K*48
    af, data = parse_nmea.parse("$GPVTG,054.7,T,034.4,M,005.5,N,010.2,K*48")
    assert af == "GPVTG"
    assert data["cog_true"] == 54.7
    assert data["cog_magnetic"] == 34.4
    assert data["sog_knots"] == 5.5
    assert data["sog_kph"] == 10.2

def test_gll():
    # $GPGLL,4916.45,N,12311.12,W,225444,A*31
    af, data = parse_nmea.parse("$GPGLL,4916.45,N,12311.12,W,225444,A*31")
    assert af == "GPGLL"
    assert data["latitude"] == pytest.approx(49.274166666666666)
    assert data["longitude"] == pytest.approx(-123.18533333333333)
    assert data["timeUTC"] == "22:54:44"
    
    with pytest.raises(Exception) as excinfo:
        # $GPGLL,4916.45,N,12311.12,W,225444,V*26
        parse_nmea.parse("$GPGLL,4916.45,N,12311.12,W,225444,V*26")
    assert "NMEAStatusError" in str(type(excinfo.value))

def test_rot():
    # $GPROT,30.0,A*02
    af, data = parse_nmea.parse("$GPROT,30.0,A*02")
    assert af == "GPROT"
    assert data["rate_of_turn"] == 30.0
    
    # $GPROT,30.0,V*15
    af, data = parse_nmea.parse("$GPROT,30.0,V*15")
    assert data["rate_of_turn"] is None

def test_rmc():
    # $GPRMC,225446,A,4916.45,N,12311.12,W,000.5,054.7,191125,020.3,E*62
    af, data = parse_nmea.parse("$GPRMC,225446,A,4916.45,N,12311.12,W,000.5,054.7,191125,020.3,E*62")
    assert af == "GPRMC"
    assert data["latitude"] == pytest.approx(49.274166666666666)
    assert data["longitude"] == pytest.approx(-123.18533333333333)
    assert data["datetimeUTC"] == "2025-11-19T22:54:46"
    assert data["sog_knots"] == 0.5
    assert data["cog_true"] == 54.7
    assert data["magnetic_variation"] == 20.3

    # Test West variation (should be negative)
    # $GPRMC,225446,A,4916.45,N,12311.12,W,000.5,054.7,191125,020.3,W*70
    af, data = parse_nmea.parse("$GPRMC,225446,A,4916.45,N,12311.12,W,000.5,054.7,191125,020.3,W*70")
    assert data["magnetic_variation"] == -20.3

def test_mwv():
    # $IIMWV,045,R,012.0,N,A*21
    af, data = parse_nmea.parse("$IIMWV,045,R,012.0,N,A*21")
    assert af == "IIMWV"
    assert data["awa"] == 45.0
    assert data["aws_knots"] == 12.0

    # True wind and different units (m/s)
    # $IIMWV,045,T,06.17,M,A*27
    af, data = parse_nmea.parse("$IIMWV,045,T,06.17,M,A*27")
    assert data["twa"] == 45.0
    assert data["tws_knots"] == pytest.approx(11.993, rel=1e-3)

def test_gga():
    # $GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47
    af, data = parse_nmea.parse("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47")
    assert af == "GPGGA"
    assert data["timeUTC"] == "12:35:19"
    assert data["latitude"] == pytest.approx(48.1173)
    assert data["longitude"] == pytest.approx(11.516666666666667)
    assert data["num_satellites"] == 8
    assert data["altitude_meter"] == 545.4

def test_rsa():
    # $IIRSA,03.2,A,02.4,A*47
    af, data = parse_nmea.parse("$IIRSA,03.2,A,02.4,A*47")
    assert af == "IIRSA"
    assert data["rudder_angle"] == 3.2

def test_vlw():
    # $IIVLW,00123.4,N,00012.3,N,00125.7,N,00013.4,N*4E
    af, data = parse_nmea.parse("$IIVLW,00123.4,N,00012.3,N,00125.7,N,00013.4,N*4E")
    assert af == "IIVLW"
    assert data["water_total_nm"] == 123.4
    assert data["water_since_reset_nm"] == 12.3
    assert data["ground_total_nm"] == 125.7
    assert data["ground_since_reset_nm"] == 13.4

    # Test short version (only water)
    # $IIVLW,00123.4,N,00012.3,N*49
    af, data = parse_nmea.parse("$IIVLW,00123.4,N,00012.3,N*49")
    assert data["water_total_nm"] == 123.4
    assert data["ground_total_nm"] is None

def test_vwr():
    # $IIVWR,148,L,02.4,N,01.2,M,04.4,K*71
    af, data = parse_nmea.parse("$IIVWR,148,L,02.4,N,01.2,M,04.4,K*71")
    assert af == "IIVWR"
    assert data["awa"] == -148.0
    assert data["aws_knots"] == 2.4
    assert data["aws_mps"] == 1.2
    assert data["aws_kph"] == 4.4
