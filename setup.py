from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="trustbit_school_book_seller",
    version="1.0.0",
    description="School Book Seller App for ERPNext - Bulk Book Item Creation",
    author="Trustbit",
    author_email="info@trustbit.in",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
