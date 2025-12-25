from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="trustbit_school_book_seller",
    version="1.0.0",
    description="Advanced Item Creation System for School Book Shops",
    author="Trustbit",
    author_email="info@trustbit.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
