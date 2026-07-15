    function createRecipeResult(image, text, title, parentContainer) {
    console.log("render recipes")
    var imgEl = document.createElement("img");
    imgEl.src = image

    var textEl = document.createElement("p");
    textEl.innerText = text

    var titleEl = document.createElement("h1");
    titleEl.innerText = title

    var recipeEl = document.createElement("div");
    recipeEl.className = "recipe"

    var recipeGroupEl = document.createElement("div");
    recipeGroupEl.className = "recipe-group"

    var recipeImgEl = document.createElement("div");
    recipeImgEl.className = "recipe-img"
    recipeImgEl.appendChild(imgEl)

    recipeGroupEl.appendChild(titleEl);
    recipeGroupEl.appendChild(textEl);

    recipeEl.appendChild(recipeImgEl);
    recipeEl.appendChild(recipeGroupEl)

    parentContainer.appendChild(recipeEl)
}
    function renderPagination(total, limit, currentOffset, result_count) {
        const paginationContainer = document.getElementById("pagination")
        const totalPages = Math.ceil(total/limit)
        const currentPage = Math.floor(currentOffset/limit) + 1

        const N = 10;

        paginationContainer.innerText = ""
        if (totalPages <=1) return

        let startPage = Math.floor((currentPage - 1) / N) * N + 1
        let endPage =  Math.min(startPage + N - 1, totalPages)

        if (startPage > 1 ) {
            const prevGroupBtn = document.createElement("button")
            prevGroupBtn.innerText = "<<"
            prevGroupBtn.onclick = () => loadRecipes((startPage - 2) * limit, limit, result_count)
            paginationContainer.appendChild(prevGroupBtn)
        }

        for (let i = startPage; i <= endPage; i++ ) {
           const pageBtn = document.createElement("button")
           pageBtn.innerText = i

           const offsetForThisPage = (i - 1) * limit
           if (currentOffset === offsetForThisPage) {
            pageBtn.classList.add("active")
           }
            pageBtn.onclick = () => loadRecipes(offsetForThisPage, limit, result_count)
            paginationContainer.appendChild(pageBtn)

        }

        if (endPage < totalPages) {
            const nextGroupBtn = document.createElement("button")
            nextGroupBtn.innerText = ">"
             nextGroupBtn.onclick = () => loadRecipes(endPage * limit, limit, result_count)
            paginationContainer.appendChild(nextGroupBtn)
        }

    }
  function loadRecipes(offset, limit, result_count) {
    var error = document.createElement("p");
    var results = document.getElementById("results")
    results.innerHTML = "Loading"
    fetch("http://localhost:8081/api/v1/recipes?offset=" + offset + "&limit=" + limit , {
            method:"GET"
        })
        .then( (resp) => {
            if(!resp.ok) {
                container.appendChild(error)
                console.error(resp)
                resp.json().then(err => {throw err})

            }
            error.remove()
            return resp.json()
        })
        .then(data => {

            results.innerText = ""
            console.log(data)
//            result_count.innerText =  data.total + " results"
            data.data.forEach(r => {
            loading.style.display = 'none';
                 console.log(r)
                createRecipeResult(r.image_path, r.text, r.title, results)
            })

            renderPagination(data.total, data.limit, data.offset, result_count)
        })
        .catch(err => {
             error.innerText = " Something went wrong"
            console.error(err)
            loading.style.display = 'none'
        })
  }