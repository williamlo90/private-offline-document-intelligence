"""Executed inside Odoo shell, only on project-07 disposable synthetic database."""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path


assert env.cr.dbname == "private_documents_odoo_lab", "Refusing non-project-07 database"
path = Path("/run/private-checklist/connections.json")
if path.exists() and env["ops.connection"].search_count([]) == 2:
    print("Existing project-07 synthetic seed and credentials preserved")
else:
    currency = env.ref("base.IDR")
    currency.active = True
    admin = env.ref("base.user_admin")
    admin.password = os.environ["PRIVATE_DOCUMENTS_ODOO_ADMIN_PASSWORD"]
    config = {}
    for tenant in ("atlas", "birch"):
        company = env["res.company"].search([("name", "=", "Project07 " + tenant.title() + " Synthetic")], limit=1)
        if not company:
            company = env["res.company"].create({"name": "Project07 " + tenant.title() + " Synthetic",
                                                  "currency_id": currency.id})
        admin.company_ids = [(4, company.id)]
        context = {"allowed_company_ids": [company.id], "tracking_disable": True,
                   "mail_create_nosubscribe": True}
        def model(name):
            return env[name].with_context(context).with_company(company)
        pricelist = model("product.pricelist").search([("name", "=", "P07-" + tenant)], limit=1)
        if not pricelist:
            pricelist = model("product.pricelist").create({"name": "P07-" + tenant,
                "company_id": company.id, "currency_id": currency.id})
        partner = model("res.partner").search([("ref", "=", "P07-" + tenant + "-customer")], limit=1)
        if not partner:
            partner = model("res.partner").create({"name": "Project07 synthetic " + tenant + " customer",
                "ref": "P07-" + tenant + "-customer", "company_id": company.id,
                "customer_rank": 1, "property_product_pricelist": pricelist.id})
        assignee = env["res.users"].search([("login", "=", "p07.assignee." + tenant)], limit=1)
        if not assignee:
            assignee = env["res.users"].with_context(no_reset_password=True).create({
                "name": "P07 Assignee " + tenant, "login": "p07.assignee." + tenant,
                "company_id": company.id, "company_ids": [(6, 0, [company.id])],
                "group_ids": [(6, 0, [env.ref("base.group_user").id,
                                     env.ref("sales_team.group_sale_salesman").id])]})
        lead = model("crm.lead").search([("name", "=", "P07 opportunity " + tenant)], limit=1)
        if not lead:
            lead = model("crm.lead").create({"name": "P07 opportunity " + tenant,
                "type": "opportunity", "partner_id": partner.id,
                "company_id": company.id, "user_id": assignee.id})
        connector = env["res.users"].search([("login", "=", "p07.connector." + tenant)], limit=1)
        if not connector:
            connector = env["res.users"].with_context(no_reset_password=True).create({
                "name": "P07 Connector " + tenant, "login": "p07.connector." + tenant,
                "company_id": company.id, "company_ids": [(6, 0, [company.id])],
                "group_ids": [(6, 0, [env.ref("base.group_portal").id,
                                     env.ref("ops_bridge.group_connector").id])]})
        if not env["ops.connection"].search([("tenant", "=", tenant)]):
            env["ops.connection"].create({"tenant": tenant, "company_id": company.id,
                "user_id": connector.id, "pricelist_id": pricelist.id})
        key = env["res.users.apikeys"].with_user(connector).sudo()._generate(
            "rpc", "p07-bridge", datetime.now() + timedelta(days=90))
        config[tenant] = {"port": 8177, "database": "private_documents_odoo_lab",
                          "tenant": tenant, "company_id": company.id,
                          "customer_id": partner.id, "opportunity_id": lead.id,
                          "assignee_id": assignee.id, "api_key": key}
    env.cr.commit()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(config), encoding="utf-8")
    temporary.replace(path)
    print("Project-07 synthetic Odoo sandbox ready: two scoped company connections")
