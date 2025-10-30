from xhtml2pdf import pisa

# enable logging
pisa.showLogging()

with open('test_pdf.html', "r") as html_file:
    html_source = html_file.read()

with open("test.pdf", "w+b") as result_file:
    # convert HTML to PDF
    pisa_status = pisa.CreatePDF(
        html_source,       # page data
        dest=result_file,  # destination file
    )

    # Check for errors
    if pisa_status.err:
        print("An error occurred!")