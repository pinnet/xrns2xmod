-- Re-saves every test song in the running Renoise, so the files carry your
-- Renoise version's format (what Xrns2XMod sees in real use).
-- Run it from Renoise's Scripting Editor (Tools > Scripting Terminal & Editor):
-- open this file, set SONGS below, press Ctrl+R. Notes are left untouched.
-- Written from the API definitions only; not yet run in Renoise.

local SONGS = "C:/path/to/xrns2xmod-tests/songs"  -- edit: folder with the .xrns files

local names = {
  "pt_effects", "pt_five_tracks", "pt_four_tracks", "pt_note_too_high",
  "pt_notes", "pt_samples_31", "pt_structure",
}

local app = renoise.app()
local index = 0
local loaded_path = nil

local function path_of(i) return SONGS .. "/" .. names[i] .. ".xrns" end

local function load_next()
  index = index + 1
  if index > #names then
    app.new_document_observable:remove_notifier(on_new_document)
    renoise.app():show_message("Re-saved " .. #names .. " songs.")
    return
  end
  loaded_path = path_of(index)
  app:load_song(loaded_path)   -- asynchronous; on_new_document fires when it is in
end

function on_new_document()
  if loaded_path then
    app:save_song_as(loaded_path)
    print("saved " .. loaded_path)
  end
  load_next()
end

app.new_document_observable:add_notifier(on_new_document)
load_next()
