# Licensing scope

The project-owned code is under the root [MIT License](LICENSE), except the
`odoo/addons/private_checklist_bridge/` addon. That addon declares LGPL-3.0 in
its Odoo manifest and remains under that license. Its pinned upstream
`ops_bridge` dependency is a separate Project 02 addon and is not included in
this repository.

Third-party Python/Node dependencies, Docker images, OCR/model assets and the
Ollama runtime retain their own licenses. The large runtime/model bundle is not
published in this Git repository. The synthetic PDFs and UI screenshots were
created for this project's documentation and tests.
