import AVFoundation
import XCTest
@testable import LatawiecShell

final class CameraGateTests: XCTestCase {
    func testAccessTurnedOffOutranksTheHardware() {
        // Whether or not a camera exists, the user's "no" is the answer
        // worth showing: it is the one they can undo.
        for hasCamera in [true, false] {
            XCTAssertEqual(cameraGate(status: .denied, hasCamera: hasCamera), .accessOff)
            XCTAssertEqual(cameraGate(status: .restricted, hasCamera: hasCamera), .accessOff)
        }
    }

    func testAnUnansweredPromptStillOpensTheCamera() {
        // The picker raises the prompt itself; refusing here would cost the
        // user the tap that grants access.
        XCTAssertEqual(cameraGate(status: .notDetermined, hasCamera: true), .ready)
        XCTAssertEqual(cameraGate(status: .notDetermined, hasCamera: false), .missing)
    }

    func testGrantedFollowsTheHardware() {
        XCTAssertEqual(cameraGate(status: .authorized, hasCamera: true), .ready)
        XCTAssertEqual(cameraGate(status: .authorized, hasCamera: false), .missing)
    }
}
