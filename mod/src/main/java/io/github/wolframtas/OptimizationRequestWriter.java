package io.github.wolframtas;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class OptimizationRequestWriter {
    private final Path configDirectory;

    public OptimizationRequestWriter(Path configDirectory) {
        this.configDirectory = configDirectory;
    }

    public Path writeFixtureRequest() throws IOException {
        Path outputDirectory = configDirectory.resolve("wolframtas");
        Files.createDirectories(outputDirectory);

        Path requestPath = outputDirectory.resolve("request.json");
        Files.write(requestPath, fixtureRequestJson().getBytes(StandardCharsets.UTF_8));
        return requestPath;
    }

    private String fixtureRequestJson() {
        return "{\n"
            + "  \"version\": 1,\n"
            + "  \"minecraft_version\": \"1.8.9\",\n"
            + "  \"angle_domain\": { \"table_size\": 65536 },\n"
            + "  \"start_state\": {\n"
            + "    \"position\": { \"x\": 0.0, \"y\": 64.0, \"z\": 0.0 },\n"
            + "    \"velocity\": { \"x\": 0.0, \"y\": 0.0, \"z\": 0.0 },\n"
            + "    \"yaw\": 0.0,\n"
            + "    \"pitch\": 0.0,\n"
            + "    \"on_ground\": true\n"
            + "  },\n"
            + "  \"keyboard_inputs\": [],\n"
            + "  \"constraints\": [],\n"
            + "  \"objectives\": [],\n"
            + "  \"solver\": { \"max_ticks\": 1, \"timeout_seconds\": 10.0 }\n"
            + "}\n";
    }
}
