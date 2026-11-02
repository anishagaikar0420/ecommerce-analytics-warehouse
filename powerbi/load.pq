// Power Query (M). In Power BI Desktop: Home > Get data > Blank query > Advanced editor, one query per block below.
// First create a text parameter named DataFolder, e.g. C:\path\to\ecommerce-analytics-warehouse\powerbi\data
// (Home > Transform data > Manage parameters > New parameter). Query names must match the table names.

// ---- fact_sales ----
let
    Source = Csv.Document(File.Contents(DataFolder & "\fact_sales.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"order_item_id", Int64.Type}, {"order_id", Int64.Type}, {"customer_key", Int64.Type}, {"product_key", Int64.Type},
        {"payment_method_key", Int64.Type}, {"date_key", Int64.Type}, {"order_status", type text}, {"quantity", Int64.Type},
        {"unit_price", Currency.Type}, {"discount", type number}, {"gross_amount", Currency.Type},
        {"net_amount", Currency.Type}, {"cost_amount", Currency.Type}})
in
    Typed

// ---- dim_customer ----
let
    Source = Csv.Document(File.Contents(DataFolder & "\dim_customer.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"customer_key", Int64.Type}, {"customer_id", Int64.Type}, {"signup_date", type date}})
in
    Typed

// ---- dim_product ----
let
    Source = Csv.Document(File.Contents(DataFolder & "\dim_product.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"product_key", Int64.Type}, {"product_id", Int64.Type}, {"list_price", Currency.Type}, {"cost", Currency.Type}})
in
    Typed

// ---- dim_date ----
let
    Source = Csv.Document(File.Contents(DataFolder & "\dim_date.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"date_key", Int64.Type}, {"full_date", type date}, {"year", Int64.Type}, {"quarter", Int64.Type},
        {"month", Int64.Type}, {"year_month", type text}, {"day_name", type text}, {"is_weekend", type logical}})
in
    Typed

// ---- dim_payment_method ----
let
    Source = Csv.Document(File.Contents(DataFolder & "\dim_payment_method.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"payment_method_key", Int64.Type}, {"payment_method", type text}})
in
    Typed

// ---- cohort_retention (stand-alone table, no relationships) ----
let
    Source = Csv.Document(File.Contents(DataFolder & "\cohort_retention.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"cohort_month", type text}, {"months_since_first", Int64.Type}, {"active_customers", Int64.Type}, {"retention_pct", type number}})
in
    Typed
