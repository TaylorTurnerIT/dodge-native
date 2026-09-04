{ lib, pkgs, ... }:

let
  nativeRuntime = with pkgs; [
    alsa-lib
    libX11
    libXcursor
    libXext
    libXfixes
    libXi
    libXinerama
    libXrandr
    libXtst
    libglvnd
    libxcb
    libxkbcommon
    mesa
  ];
  nativeLibraryPath = lib.makeLibraryPath nativeRuntime;
in
{
  packages = [
    pkgs.cargo
    pkgs.clippy
    pkgs.rust-analyzer
    pkgs.rustc
    pkgs.rustfmt
    pkgs.xorg.xorgserver
  ];

  enterShell = ''
    export LD_LIBRARY_PATH=${nativeLibraryPath}:"$LD_LIBRARY_PATH"
    export LIBGL_DRIVERS_PATH=${pkgs.mesa}/lib/dri:"$LIBGL_DRIVERS_PATH"
  '';
}
