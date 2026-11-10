import DivKit
import LayoutKit
import MapKit
import UIKit
import os

private let log = Logger(subsystem: "io.github.krszozda.latawiec", category: "map")

/// Renders the DSL's Map, which DivKit knows only as a custom block.
///
/// MapKit draws it, so the map costs the app no dependency and no API key;
/// `tiles` swaps Apple's own rendering for raster tiles, which is how an
/// app makes both shells look the same.
final class MapBlockFactory: DivCustomBlockFactory {
    /// One view per place in the card, not per render. A card re-renders
    /// on every live message, every poll and every variable the shell
    /// writes; building a new MKMapView each time would throw away what
    /// the user panned to, mid-gesture.
    private var views: [String: MapView] = [:]

    func makeBlock(data: DivCustomData, context: DivBlockModelingContext) -> Block {
        guard data.name == "latawiec_map" else {
            log.warning("unknown custom block \(data.name)")
            return EmptyBlock.zeroSized
        }
        let path = context.parentPath.description
        let view = views[path] ?? MapView()
        views[path] = view
        view.apply(props: data.data)
        return GenericViewBlock(view: view)
    }
}

final class MapView: UIView {
    private let map = MKMapView()
    private var overlay: MKTileOverlay?

    override init(frame: CGRect) {
        super.init(frame: frame)
        map.translatesAutoresizingMaskIntoConstraints = false
        addSubview(map)
        NSLayoutConstraint.activate([
            map.topAnchor.constraint(equalTo: topAnchor),
            map.bottomAnchor.constraint(equalTo: bottomAnchor),
            map.leadingAnchor.constraint(equalTo: leadingAnchor),
            map.trailingAnchor.constraint(equalTo: trailingAnchor),
        ])
        map.delegate = self
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }

    /// What the server last asked for, so a re-render can tell a new place
    /// from the same place — and leave a map the user has moved alone.
    private var placed: (Double, Double, Double)?

    func apply(props: [String: Any]) {
        let latitude = double(props["latitude"]) ?? 0
        let longitude = double(props["longitude"]) ?? 0
        let zoom = double(props["zoom"]) ?? 14
        if placed.map({ $0 != (latitude, longitude, zoom) }) ?? true {
            placed = (latitude, longitude, zoom)
            // A zoom level is a tile-pyramid step: each one halves the
            // span, with the whole world across the screen at zoom 1.
            let span = 180 / pow(2, zoom - 1)
            map.setRegion(
                MKCoordinateRegion(
                    center: CLLocationCoordinate2D(latitude: latitude, longitude: longitude),
                    span: MKCoordinateSpan(
                        // A span reaching past a pole is refused outright,
                        // leaving the map wherever it already was.
                        latitudeDelta: min(span, (90 - abs(latitude)) * 2),
                        longitudeDelta: span * 2
                    )
                ),
                animated: false
            )
        }

        map.removeAnnotations(map.annotations)
        for pin in props["markers"] as? [[String: Any]] ?? [] {
            guard let pinLatitude = double(pin["latitude"]),
                  let pinLongitude = double(pin["longitude"]) else { continue }
            let annotation = MKPointAnnotation()
            annotation.coordinate = CLLocationCoordinate2D(
                latitude: pinLatitude, longitude: pinLongitude
            )
            annotation.title = pin["label"] as? String
            map.addAnnotation(annotation)
        }

        overlay.map(map.removeOverlay)
        overlay = nil
        if let template = props["tiles"] as? String, !template.isEmpty {
            let tiles = MKTileOverlay(urlTemplate: template)
            // Apple's own labels would sit under someone else's streets.
            tiles.canReplaceMapContent = true
            map.addOverlay(tiles, level: .aboveLabels)
            overlay = tiles
        }
    }

    private func double(_ value: Any?) -> Double? {
        value as? Double ?? (value as? NSNumber)?.doubleValue
    }
}

extension MapView: MKMapViewDelegate {
    func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
        guard let tiles = overlay as? MKTileOverlay else {
            return MKOverlayRenderer(overlay: overlay)
        }
        return MKTileOverlayRenderer(tileOverlay: tiles)
    }
}
