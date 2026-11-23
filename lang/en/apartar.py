"""WORKSPACE · lang/en/apartar — archive an agent or remove it from Workspace (agente_apartar): the one-line notices,
what is worth knowing first, and the errors."""

STRINGS = {
    "apartar.archivado": "Archived {n}. Its folder and its sessions are still in {p}.",
    "apartar.quitado": "Removed {n} from Workspace on this computer. Its folder stays in {p}.",
    "apartar.volvio": "{n} is back.",
    "apartar.volvio.sin_carpeta": "Its folder is not on this computer yet ({p}): once it finishes syncing, it is "
                                  "ready.",
    "apartar.terminal": "{n} is archived: bring it back in the hub, Agents › This machine › Archived (its folder is "
                        "still in {p}).",
    "apartar.y": "and",
    "apartar.aviso.actual": "You are talking to {n} right now: the open conversation keeps going, but it stops showing "
                            "in the lists.",
    "apartar.aviso.ultimo": "It is your only agent: the hub stays empty until you bring it back or add another one.",
    "apartar.aviso.sesion": "It has something open right now ({s}): nothing is closed or lost, it just stops showing "
                            "in the lists.",
    "apartar.aviso.coordina": "{n} coordinates other agents: it sends tasks to {a}. Without it, nobody receives those "
                              "tasks back.",
    "apartar.aviso.a_medias": "Its folder is not complete on this computer (it may still be syncing): it is not "
                              "touched.",
    "apartar.sesion.sin_nombre": "a session",
    "apartar.job.crear": "it is being created",
    "apartar.job.cargar": "it is being connected",
    "apartar.err.guardar": "Could not save its record: nothing was changed.",
    "apartar.err.archivar": "Could not archive it: {e}",
    "apartar.err.no_esta": "I cannot find {n} among the archived agents.",
    "apartar.err.otro": "There is already another agent called {n} on this computer: I did not overwrite it. The "
                        "archived one is still saved.",
    "apartar.err.volver": "Could not bring it back: the registry could not be written.",
}
