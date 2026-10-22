// Read-only waypoint query against the pinned AzerothCore Detour files.
#include "MapDefines.h"
#include "DetourNavMeshQuery.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using Point = std::array<float, 3>;
Point toDetour(Point p) { return {p[1], p[2], p[0]}; }
Point toWorld(Point p) { return {p[2], p[0], p[1]}; }
void require(bool ok, const std::string& message) {
    if (!ok) throw std::runtime_error(message);
}
void checked(dtStatus status, const std::string& operation) {
    require(status == DT_SUCCESS, operation + " failed, partial, or exceeded bounds");
}
void readBytes(std::ifstream& file, void* data, std::size_t size, const std::string& name) {
    require(bool(file.read(static_cast<char*>(data), size)), "cannot read " + name);
}
float number(const char* text) {
    std::size_t used = 0;
    float value = std::stof(text, &used);
    require(used == std::string(text).size() && std::isfinite(value) && std::abs(value) < 17066,
            "invalid coordinate");
    return value;
}
void printPoint(Point p) {
    std::cout << '[' << p[0] << ',' << p[1] << ',' << p[2] << ']';
}
float distance(Point a, Point b) {
    return std::hypot(std::hypot(a[0]-b[0], a[1]-b[1]), a[2]-b[2]);
}

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--self-check") {
            Point p{-8911.4f, -166.328f, 82.2088f};
            require(toDetour(p) == Point{p[1], p[2], p[0]} && toWorld(toDetour(p)) == p,
                    "coordinate roundtrip");
            std::cout << "{\"coordinate_roundtrip\":true}\n";
            return 0;
        }
        require(argc == 8 || (argc == 10 && std::string(argv[8]) == "--base"),
                "usage: navmesh_path MAP SX SY SZ EX EY EZ [--base MMAPS_DIRECTORY]");
        std::size_t used = 0;
        int map = std::stoi(argv[1], &used);
        require(used == std::string(argv[1]).size() && map >= 0 && map <= 999, "invalid map");
        Point worldStart{number(argv[2]), number(argv[3]), number(argv[4])};
        Point worldEnd{number(argv[5]), number(argv[6]), number(argv[7])};
        require(distance(worldStart, worldEnd) <= 2000, "route exceeds 2000-yard local query limit");
        std::string base = argc == 10 ? argv[9] : "./mmaps";
        char name[64];
        std::snprintf(name, sizeof(name), "%03d.mmap", map);
        std::string paramsName = base + "/" + name;
        std::ifstream paramsFile(paramsName, std::ios::binary);
        dtNavMeshParams params{};
        readBytes(paramsFile, &params, sizeof(params), paramsName);
        require(paramsFile.peek() == EOF && params.maxTiles > 0 && params.maxTiles <= 16384 &&
                std::isfinite(params.tileWidth) && params.tileWidth > 0 &&
                std::isfinite(params.tileHeight) && params.tileHeight > 0 &&
                std::all_of(params.orig, params.orig + 3, [](float v) { return std::isfinite(v); }),
                "invalid mmap parameters");
        std::unique_ptr<dtNavMesh, decltype(&dtFreeNavMesh)> mesh(dtAllocNavMesh(), dtFreeNavMesh);
        require(bool(mesh), "navmesh allocation failed");
        checked(mesh->init(&params), "navmesh init");
        // shortcut: local bounding rectangle plus one tile margin; split longer trips into local legs.
        auto grid = [](float v) { return int(std::floor(32.0 - double(v) / 533.3333333333333)); };
        int xmin = std::max(0, std::min(grid(worldStart[0]), grid(worldEnd[0])) - 1);
        int xmax = std::min(63, std::max(grid(worldStart[0]), grid(worldEnd[0])) + 1);
        int ymin = std::max(0, std::min(grid(worldStart[1]), grid(worldEnd[1])) - 1);
        int ymax = std::min(63, std::max(grid(worldStart[1]), grid(worldEnd[1])) + 1);
        std::vector<std::string> loaded;
        for (int x = xmin; x <= xmax; ++x) for (int y = ymin; y <= ymax; ++y) {
            std::snprintf(name, sizeof(name), "%03d%02d%02d.mmtile", map, x, y);
            std::string path = base + "/" + name;
            std::ifstream file(path, std::ios::binary);
            if (!file) continue; // Ocean/absent neighboring tiles are not necessarily errors.
            MmapTileHeader header;
            readBytes(file, &header, sizeof(header), path);
            require(header.mmapMagic == MMAP_MAGIC && header.mmapVersion == MMAP_VERSION &&
                    header.dtVersion == DT_NAVMESH_VERSION && header.size >= sizeof(dtMeshHeader) &&
                    header.size <= 64 * 1024 * 1024, "invalid tile header: " + path);
            std::unique_ptr<unsigned char, decltype(&dtFree)> data(
                static_cast<unsigned char*>(dtAlloc(header.size, DT_ALLOC_PERM)), dtFree);
            require(bool(data), "tile allocation failed");
            readBytes(file, data.get(), header.size, path);
            require(file.peek() == EOF, "unexpected tile trailing data: " + path);
            checked(mesh->addTile(data.get(), header.size, DT_TILE_FREE_DATA, 0, nullptr), "add " + path);
            data.release();
            loaded.push_back(name);
        }
        require(!loaded.empty(), "no local navmesh tiles loaded");
        dtNavMeshQuery query;
        checked(query.init(mesh.get(), 8192), "query init");
        dtQueryFilter filter;
        filter.setIncludeFlags(NAV_GROUND);
        filter.setExcludeFlags(NAV_WATER | NAV_MAGMA | NAV_SLIME);
        Point start = toDetour(worldStart), end = toDetour(worldEnd), snappedStart{}, snappedEnd{};
        auto snap = [&](Point p, Point& snapped) {
            const float extents[3]{2, 3, 2};
            dtPolyRef refs[256], best = 0;
            int count = 0;
            checked(query.queryPolygons(p.data(), extents, &filter, refs, &count, 256), "endpoint search");
            float bestHeight = 1e9f, bestHorizontal = 1e9f;
            for (int i = 0; i < count; ++i) {
                const dtMeshTile* tile; const dtPoly* poly;
                checked(mesh->getTileAndPolyByRef(refs[i], &tile, &poly), "endpoint polygon");
                if (poly->getType() != DT_POLYTYPE_GROUND) continue;
                Point candidate{};
                checked(query.closestPointOnPoly(refs[i], p.data(), candidate.data(), nullptr), "endpoint projection");
                float h = std::abs(candidate[1] - p[1]);
                float horizontal = std::hypot(candidate[0]-p[0], candidate[2]-p[2]);
                if (h > 3 || horizontal > 2) continue;
                if (h < bestHeight || (h == bestHeight && horizontal < bestHorizontal)) {
                    bestHeight = h; bestHorizontal = horizontal; best = refs[i]; snapped = candidate;
                }
            }
            require(best != 0, "no ground polygon within 2 horizontal / 3 vertical yards of endpoint");
            return best;
        };
        dtPolyRef startRef = snap(start, snappedStart), endRef = snap(end, snappedEnd);
        float directHit = 0, hitNormal[3];
        dtPolyRef directPolys[2048]; int directCount = 0;
        checked(query.raycast(startRef, snappedStart.data(), snappedEnd.data(), &filter,
                              &directHit, hitNormal, directPolys, &directCount, 2048), "direct wall check");
        dtPolyRef corridor[2048]; int count = 0;
        checked(query.findPath(startRef, endRef, snappedStart.data(), snappedEnd.data(), &filter,
                               corridor, &count, 2048), "findPath");
        require(count > 0 && corridor[count-1] == endRef, "incomplete route, missing tiles or disconnected ground");
        for (int i = 0; i < count; ++i) {
            const dtMeshTile* tile; const dtPoly* poly;
            checked(mesh->getTileAndPolyByRef(corridor[i], &tile, &poly), "corridor polygon");
            require(poly->getType() == DT_POLYTYPE_GROUND, "off-mesh connection rejected");
        }
        Point points[4096]; unsigned char flags[4096]; dtPolyRef pointRefs[4096]; int pointCount = 0;
        checked(query.findStraightPath(snappedStart.data(), snappedEnd.data(), corridor, count,
                points[0].data(), flags, pointRefs, &pointCount, 4096, DT_STRAIGHTPATH_ALL_CROSSINGS), "waypoints");
        require(pointCount > 0 && (flags[pointCount-1] & DT_STRAIGHTPATH_END), "incomplete waypoints");
        float length = 0;
        for (int i = 0; i < pointCount; ++i) {
            require(!(flags[i] & DT_STRAIGHTPATH_OFFMESH_CONNECTION), "off-mesh waypoint rejected");
            Point ground{};
            // Portal-edge rounding can put a crossing just outside its entering polygon.
            checked(query.closestPointOnPoly(pointRefs[i] ? pointRefs[i] : endRef,
                    points[i].data(), ground.data(), nullptr), "ground height");
            points[i] = ground;
            if (i) length += distance(points[i-1], points[i]);
        }
        std::cout << std::setprecision(9) << "{\"map\":" << map
                  << ",\"client_walk_verified\":false,\"ground_only\":true,\"requested_start\":";
        printPoint(worldStart); std::cout << ",\"requested_end\":"; printPoint(worldEnd);
        std::cout << ",\"start_snap_distance\":" << distance(start, snappedStart)
                  << ",\"end_snap_distance\":" << distance(end, snappedEnd)
                  << ",\"path_length\":" << length << ",\"direct_distance\":" << distance(start, end)
                  << ",\"direct_segment_blocked\":" << (directHit < 1 ? "true" : "false")
                  << ",\"corridor_polygons\":" << count << ",\"tiles\":[";
        for (std::size_t i = 0; i < loaded.size(); ++i) std::cout << (i ? ",\"" : "\"") << loaded[i] << '"';
        std::cout << "],\"waypoints\":[";
        for (int i = 0; i < pointCount; ++i) { if (i) std::cout << ','; printPoint(toWorld(points[i])); }
        std::cout << "]}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "navmesh_path: " << error.what() << '\n';
        return 1;
    }
}
