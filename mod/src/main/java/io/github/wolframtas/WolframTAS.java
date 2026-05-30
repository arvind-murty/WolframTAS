package io.github.wolframtas;

import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.common.event.FMLInitializationEvent;
import net.minecraftforge.fml.common.event.FMLPreInitializationEvent;

@Mod(modid = WolframTAS.MOD_ID, name = WolframTAS.NAME, version = WolframTAS.VERSION, clientSideOnly = true)
public final class WolframTAS {
    public static final String MOD_ID = "wolframtas";
    public static final String NAME = "WolframTAS";
    public static final String VERSION = "0.1.0-SNAPSHOT";

    @Mod.Instance(MOD_ID)
    public static WolframTAS instance;

    private OptimizationRequestWriter requestWriter;

    @Mod.EventHandler
    public void preInit(FMLPreInitializationEvent event) {
        this.requestWriter = new OptimizationRequestWriter(event.getModConfigurationDirectory().toPath());
    }

    @Mod.EventHandler
    public void init(FMLInitializationEvent event) {
        // GUI registration and keybindings will be wired here.
    }

    public OptimizationRequestWriter getRequestWriter() {
        return requestWriter;
    }
}
