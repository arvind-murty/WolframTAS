package io.github.wolftas;

import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.common.event.FMLInitializationEvent;
import net.minecraftforge.fml.common.event.FMLPreInitializationEvent;

@Mod(modid = WolfTAS.MOD_ID, name = WolfTAS.NAME, version = WolfTAS.VERSION, clientSideOnly = true)
public final class WolfTAS {
    public static final String MOD_ID = "wolftas";
    public static final String NAME = "WolfTAS";
    public static final String VERSION = "0.1.0-SNAPSHOT";

    @Mod.Instance(MOD_ID)
    public static WolfTAS instance;

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
