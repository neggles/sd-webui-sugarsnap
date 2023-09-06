import logging
from pathlib import Path

import gradio as gr
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from modules import script_callbacks, shared, launch_utils, scripts, extensions


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

photopea_ext_dir = Path(scripts.basedir())
photopea_app_dir = photopea_ext_dir.joinpath("app")

opt_section = ("photopea", "Photopea")
update_success = False


def _get_setting(name: str, default=None):
    return shared.opts.data.get(f"photopea_{name}", default)


def update_photopea(repo_url: str, target_dir: Path = photopea_app_dir, commit_hash: str = "") -> bool:
    global update_success
    try:
        # logger.info("Installing Photopea...")
        launch_utils.git_clone(
            url=repo_url, dir=target_dir, name="Photopea", commithash=commit_hash)
        # logger.info("Photopea installation up-to-date.")
        return True
    except Exception:
        logger.critical(
            "Failed to update Photopea, will not load!", exc_info=True)
        return False


def on_before_ui() -> None:
    global update_success
    repo_url = _get_setting(
        "repo_url", "https://git.nixnet.services/DUOLabs333/Photopea-Offline.git")
    commit_hash = _get_setting("commit_hash", "")
    update_success = update_photopea(
        repo_url=repo_url,
        target_dir=photopea_app_dir,
        commit_hash=commit_hash if commit_hash != "" else None,
    )


def on_ui_settings() -> None:
    shared.opts.add_option(
        "photopea_repo_url",
        shared.OptionInfo(
            default="https://git.nixnet.services/DUOLabs333/Photopea-Offline.git",
            label="Photopea repository URL",
            component=gr.Textbox,
            component_args={"interactive": True, "max_lines": 1},
            section=opt_section,
        ),
    )
    shared.opts.add_option(
        "photopea_commit_hash",
        shared.OptionInfo(
            default="",
            label="Photopea repository commit hash",
            component=gr.Textbox,
            component_args={"interactive": True, "max_lines": 1},
            section=opt_section,
        ),
    )


def on_ui_tabs():
    with gr.Blocks(analytics_enabled=False) as photopea_tab:
        # Check if Controlnet is installed and enabled in settings, so we can show or hide the "Send to Controlnet" buttons.
        controlnet_exists = False
        for extension in extensions.active():
            if "controlnet" in extension.name:
                controlnet_exists = True
                break

        with gr.Row():
            show_photopea = gr.Button(
                value='Load Photopea', elem_id="photopeaLoadButton")

        with gr.Row(elem_id="photopeaIframeContainer"):
            pass

        with gr.Row():
            gr.Checkbox(
                label="Active Layer Only",
                info="If true, instead of sending the flattened image, will send just the currently selected layer.",
                elem_id="photopea-use-active-layer-only",
            )
            # Controlnet might have more than one model tab (set by the 'control_net_max_models_num' setting).
            try:
                num_controlnet_models = shared.opts.control_net_max_models_num
            except:
                num_controlnet_models = 1

            select_target_index = gr.Dropdown(
                [str(i) for i in range(num_controlnet_models)],
                label="ControlNet model index",
                value="0",
                interactive=True,
                visible=num_controlnet_models > 1,
            )

            # Just create the size slider here. We'll modify the page via the js bindings.
            gr.Slider(
                minimum=512,
                maximum=2160,
                value=768,
                step=10,
                label="iFrame height",
                interactive=True,
                elem_id="photopeaIframeSlider",
            )

        with gr.Row():
            with gr.Column():
                gr.HTML(
                    """<b>Controlnet extension not found!</b> Either <a href="https://github.com/Mikubill/sd-webui-controlnet" target="_blank">install it</a>, or activate it under Settings.""",
                    visible=not controlnet_exists,
                )
                send_t2i_cn = gr.Button(
                    value="Send to txt2img ControlNet", visible=controlnet_exists
                )
                send_extras = gr.Button(value="Send to Extras")

            with gr.Column():
                send_i2i = gr.Button(value="Send to img2img")
                send_i2i_cn = gr.Button(
                    value="Send to img2img ControlNet", visible=controlnet_exists
                )
            with gr.Column():
                send_selection_inpaint = gr.Button(value="Inpaint selection")

        with gr.Row():
            gr.HTML(
                """<font size="small"><p align="right">Consider supporting Photopea by <a href="https://www.photopea.com/api/accounts" target="_blank">going Premium</a>!</font></p>"""
            )
        # The getAndSendImageToWebUITab in photopea-bindings.js takes the following parameters:
        #  webUiTab: the name of the tab. Used to find the gallery via DOM queries.
        #  sendToControlnet: if true, tries to send it to a specific ControlNet widget, otherwise, sends to the native WebUI widget.
        #  controlnetModelIndex: the index of the desired controlnet model tab.
        send_t2i_cn.click(
            None,
            select_target_index,
            None,
            _js="(i) => {getAndSendImageToWebUITab('txt2img', true, i)}",
        )
        send_extras.click(
            None,
            select_target_index,
            None,
            _js="(i) => {getAndSendImageToWebUITab('extras', false, i)}",
        )
        send_i2i.click(
            None,
            select_target_index,
            None,
            _js="(i) => {getAndSendImageToWebUITab('img2img', false, i)}",
        )
        send_i2i_cn.click(
            None,
            select_target_index,
            None,
            _js="(i) => {getAndSendImageToWebUITab('img2img', true, i)}",
        )
        send_selection_inpaint.click(
            fn=None, _js="sendImageWithMaskSelectionToWebUi")

        show_photopea.click(
            fn=None,
            _js="loadPhotopea"
        )

    return [(photopea_tab, "Photopea", "photopea_embed")]


def on_app_started(_: gr.Blocks, app: FastAPI) -> None:
    global update_success
    if update_success is True:
        # logger.info("Photopea update successful, mounting app...")
        # Create a static app from the photopea app directory
        photopea_app = StaticFiles(
            directory=photopea_app_dir.joinpath("www.photopea.com"),
            html=True,
        )
        # Mount it at /photopea
        app.mount(path="/photopea", app=photopea_app, name="photopea")
    else:
        logger.warn("Photopea not loaded due to update failure!")


# register callbacks

# this is called first, before the UI is built, so we'll update photopea here
script_callbacks.on_before_ui(on_before_ui)

# when the UI is built, we'll add the options and (if update was successful) the tab
script_callbacks.on_ui_settings(on_ui_settings)
script_callbacks.on_ui_tabs(on_ui_tabs)

# then when the app is started, we'll mount the static webapp at /photopea
script_callbacks.on_app_started(on_app_started)
