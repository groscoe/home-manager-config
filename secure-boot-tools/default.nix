{ lib, pkgs, ... }:
let
  fixedSbsigntool = pkgs.sbsigntool.overrideAttrs (old: {
    pname = "sbsigntool-fixed";
    # Upstream db731f0 fixes false successes with unrelated trust certificates.
    # Keep this patch until the pinned package includes the upstream fix.
    patches = (old.patches or [ ]) ++ [ ./fix-intermediate-validation.patch ];
  });
in
{
  home.packages = lib.optionals pkgs.stdenv.hostPlatform.isLinux [ fixedSbsigntool ];
}
