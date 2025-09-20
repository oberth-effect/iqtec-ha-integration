{
  lib,
  buildHomeAssistantComponent,
  piqtec,
}:

buildHomeAssistantComponent rec {
  owner = "oberth-effect";
  domain = "iqtec";
  version = "99.99.99";

  src = "./.";

  dependencies = [
    piqtec
  ];


  meta = rec {
    description = "Home Assistant IQtec Integration";
    homepage = "https://github.com/oberth-effect/iqtec-ha-integration";
    maintainers = with lib.maintainers; [ oberth-effect ];
    license = lib.licenses.cc-by-nc-sa-40;
  };
}