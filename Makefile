DOCKER_IMAGE = casual_scraper
DOCKER_TAG = latest
DOCKER_IMAGE_FULL = $(DOCKER_IMAGE):$(DOCKER_TAG)
GITHUB_DOCKER = docker.pkg.github.com/$(shell echo ${GITHUB_REPOSITORY} | tr A-Z a-z)/$(DOCKER_IMAGE_FULL)


.PHONY: build
build:
	docker build --pull -t $(DOCKER_IMAGE_FULL) .


.PHONY: bash
bash:
	docker run -it --rm $(DOCKER_IMAGE_FULL) bash


.PHONY: run
run:
	docker run --rm -e MAILGUN -e API_KEY -e EMAILS -e MONGO_URI $(DOCKER_IMAGE_FULL) python -m CasualScraper.main


.PHONY: build_with_github
build_with_github:
	docker pull $(GITHUB_DOCKER) || true
	docker build --pull -t $(DOCKER_IMAGE_FULL) --cache-from=$(GITHUB_DOCKER) .
	docker tag $(DOCKER_IMAGE_FULL) $(GITHUB_DOCKER)
	docker push $(GITHUB_DOCKER)

