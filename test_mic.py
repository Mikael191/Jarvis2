import sounddevice as sd

try:
    print("Testing default device...")
    with sd.RawInputStream(
        samplerate=16000, blocksize=512, dtype="int16", channels=1
    ) as stream:
        print("Stream opened.")
        data, overflow = stream.read(512)
        print("Read", len(data), "bytes.")
except Exception as e:
    print(f"Failed default: {e}")
    try:
        print("Fallback testing device 1 (WO Mic)...")
        with sd.RawInputStream(
            device=1, samplerate=16000, blocksize=512, dtype="int16", channels=1
        ) as stream2:
            print("Stream 2 opened.")
            data, overflow = stream2.read(512)
            print("Read", len(data), "bytes on WO Mic.")
    except Exception as e2:
        print(f"Failed fallback: {e2}")
